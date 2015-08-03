import os
import json
from flask import Flask
from flask import render_template, send_from_directory, Response, url_for, request, abort, redirect, flash
from flask import jsonify, _app_ctx_stack
from sqlite3 import dbapi2 as sqlite3
import time
from datetime import datetime


# app initialization
app = Flask(__name__)
app.config.update(
	DATABASE = 'todo.db',
	DEBUG = True,
	SECRET_KEY = '105b01725ad4a7e119e0d4927b8f8706d9bf28a7d138d080'
)

# DB utility 

@app.teardown_appcontext
def close_database(exception):
    """Closes the database again at the end of the request."""
    top = _app_ctx_stack.top
    if hasattr(top, 'sqlite_db'):
        top.sqlite_db.close()


def init_db():
    """Creates the database tables."""
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()


def dict_factory(cursor, row):
	d = {}
	for index, col in enumerate(cursor.description):
		d[col[0]] = row[index]
	return d

def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    top = _app_ctx_stack.top
    if not hasattr(top, 'sqlite_db'):
        top.sqlite_db = sqlite3.connect(app.config['DATABASE'])
        # use dict_factory because we jsonify all results
        top.sqlite_db.row_factory = dict_factory 
    return top.sqlite_db

def query_db(query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def create_item(title):
	db = get_db()
	cur = db.execute('''insert into TodoItem (title, creation_date, completed) values (?, ?, ?)''',
	[request.form['title'], int(time.time()), False])
	db.commit()
	app.logger.debug("last insert item_id: {}".format(cur.lastrowid))
	lastObject = query_db('''select * from TodoItem where item_id == ?''', [cur.lastrowid], one=True)
	app.logger.debug("last insert item: {}".format(lastObject))
	return lastObject


# test controllers

@app.route('/test/list')
def check():
	items = [{'a': 1, 'b': 'bbb'}, {'a': 2, 'b': None}]
	return jsonify(results = items)

@app.route('/test/formtoparams', methods=['POST'])
def formToParams():
	paramsStr = ', '.join(['%s = "%s"' % (key, value) for (key, value) in request.form.items()])
	return jsonify(params = paramsStr)

# main controllers

@app.route('/items', methods=['GET'])
def items():
	items = query_db('''select * from TodoItem''')
	app.logger.debug('items: {}'.format(items))
	return jsonify(results=items)

@app.route('/item', methods=['POST'])
def addItem():
	error = None
	if request.form['title']:
		task = query_db('''select title from TodoItem where title = ?''', [request.form['title']], one=True)
		if not task:
			return jsonify(**create_item(request.form['title']))
		else:
			error = 'Item with title {} already exist. Title should be unique.'.format(request.form['title'])
	else:
		error = 'Item title not specified'

	app.logger.debug('error: {}'.format(error))
	return jsonify(error=error), 400


# Item details

def get_item(item_id):
	app.logger.debug('getting info for item with id {}'.format(item_id))
	item = query_db('''select * from TodoItem where item_id = ?''', [item_id], one=True)
	return jsonify(**item)

def edit_item(item_id, form):
	app.logger.debug('editing item with id {}. new fields: {}'.format(item_id, form))
	d = form.copy()
	if 'completed' in form:
		if d['completed'] == '1':
			app.logger.debug('completed is 1')
			d['completion_date'] = int(time.time())
		else:
			app.logger.debug('completed is 0')
			d['completion_date'] = None

	
	for (key, value) in d.items():
		if value is None or value is 'null':
			d[key] = 'NULL'
		else:
			d[key] = '"' + str(value) + '"' 

	paramsStr = ', '.join(['%s = %s' % (key, value) for (key, value) in d.items()])
	query = 'update TodoItem set ' + paramsStr + " where item_id = ?"
	app.logger.debug('update query: "' + query + '"')
	db = get_db()
	try:
		db.execute(query, [item_id])
	except sqlite3.OperationalError, msg:
		return jsonify(error='Error updating TodoItem: {}'.format(msg))
	
	db.commit()
	lastObject = query_db('''select * from TodoItem where item_id == ?''', [item_id], one=True)
	app.logger.debug("last insert item: {}".format(lastObject))
	return jsonify(**lastObject)

def delete_item(item_id):
	app.logger.debug('deleting item with id {}'.format(item_id))
	db = get_db()
	db.execute('''delete from TodoItem where item_id = ?''', [item_id])
	db.commit()
	return jsonify(results="Item removed")

@app.route('/item/<item_id>', methods=['GET', 'POST', 'DELETE'])
def itemEndpoint(item_id):
	isItemExist = query_db('''select item_id from TodoItem where item_id = ?''', [item_id], one=True)
	if isItemExist is None:
		return jsonify(error='No item with id={}'.format(item_id)), 404
	if request.method == 'GET':
		return get_item(item_id)
	elif request.method == 'POST':
		updatedItem = edit_item(item_id, request.form)
		return updatedItem
	elif request.method == 'DELETE':
		return delete_item(item_id)
	return jsonify(error='Method not supported'), 400


# HTML Console controllers

@app.route('/')
def index():
	return redirect(url_for('app_console'))

@app.route('/app_console')
def app_console():
	return render_template('index.html', items=query_db('''select * from TodoItem'''))

@app.route('/w_add_item', methods=['POST'])
def w_add_item():
	if request.form['title']:
		task = query_db('''select title from TodoItem where title = ?''', [request.form['title']], one=True)
		if not task:
			create_item(request.form['title'])
		else:
			flash('Item with title {} already exist. Title should be unique.'.format(request.form['title']))
	else:
		flash('Item title not specified')
	
	flash('New item created')
	return redirect(url_for('app_console'))

@app.route('/w_complete_item', methods=['POST'])
def w_complete_item():
	app.logger.debug('request: {}'.format(request.form))
	if request.form['item_id']:	
		task = query_db('''select * from TodoItem where item_id = ?''', [request.form['item_id']], one=True)
		app.logger.debug('checkpoint task: {}'.format(task))
		if task["completed"] is 1:	
			app.logger.debug('checkpoint Uncomplete-item')
			params = {"completed": '0', "completion_date": None}
			edit_item(request.form['item_id'], params)
		else:
			app.logger.debug('checkpoint Complete-item')
			params = {"completed": '1', "completion_date": int(time.time())}
			edit_item(request.form['item_id'], params)
		
	return redirect(url_for('app_console'))

@app.route('/w_wipe_all')
def w_wipe_all():
	get_db().close()
	init_db()
	return redirect(url_for('app_console'))

# special file handlers
@app.route('/favicon.ico')
def favicon():
	return send_from_directory(os.path.join(app.root_path, 'static'), 'img/favicon.ico')

def format_datetime(timestamp):
    """Format a timestamp for display."""
    return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d @ %H:%M')

# error handlers
@app.errorhandler(404)
def page_not_found(e):
	return render_template('404.html'), 404

app.jinja_env.filters['datetimeformat'] = format_datetime

# server launchpad
if __name__ == '__main__':
	init_db()
	port = int(os.environ.get('PORT', 5000))
	app.run(host='127.0.0.1', port=port)

	
