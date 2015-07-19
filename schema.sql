drop table if exists TodoItem;
create table TodoItem (
  item_id integer primary key autoincrement,
  title text not null,
  creation_date integer not null,
  completed boolean not null,
  completion_date integer
);
