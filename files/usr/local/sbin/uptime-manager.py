#!/usr/bin/python2
# -*- coding: utf-8 -*-
# --------------------------------------------------------------------------
# Uptime-Manager: keep a table of required uptimes of a computer
#
# Author: Bernhard Bablok
# License: GPL3
#
# Website: https://github.com/bablokb/uptime-manager
#
# --------------------------------------------------------------------------

VERSION=1      # increase with incompatible changes

LIST_HEADER = "Owner    | Label      | Type | Value      | State | Time"
LIST_SEP    = "---------|------------|------|------------|-------|-----"
LIST_FORMAT = "{0:8} | {1:10} | {2:4} | {3:10} | {4:5d} | {5:8}"

# --- system-imports   -----------------------------------------------------

import argparse
import sys, os, datetime, sqlite3, locale

# ---------------------------------------------------------------------------
# --- helper-class for options   --------------------------------------------

class Options(object):
  pass

# ---------------------------------------------------------------------------
# --- helper-class for messages   -------------------------------------------

class Msg(object):
  """simple class for messages """

  MSG_LEVELS={
    "TRACE":0,
    "DEBUG":1,
    "INFO":2,
    "WARN":3,
    "ERROR":4,
    "NONE":5
    }
  def __init__(self,level):
    self._level = level

  # --- print a message   ---------------------------------------------------
  
  def msg(self,msg_level,text,nl=True):
    """Ausgabe einer Meldung"""
    if Msg.MSG_LEVELS[msg_level] >= Msg.MSG_LEVELS[self._level]:
      if nl:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sys.stderr.write("[" + msg_level + "] " + "[" + now + "] " + text + "\n")
      else:
        sys.stderr.write(text)
        sys.stderr.flush()

# ---------------------------------------------------------------------------

# --- isoweekday of given date   --------------------------------------------

def dow(date):
  """ return isoweekday of given date """

  return date.isoweekday()

# --- day of month of given date   ------------------------------------------

def dom(date):
  """ return day of given date """

  return date.day

# --- date of given date   --------------------------------------------------

def dates(date):
  """ return date of given date """

  return date.strftime("%Y-%m-%d")

# --- open database   -------------------------------------------------------

def open_db(options):
  """ open database and return reference """

  logger.msg("DEBUG","opening database: %s" % options.db_name)
  try:
    options.db = sqlite3.connect(options.db_name,
                                 detect_types=sqlite3.PARSE_DECLTYPES)
    return options.db
  except Exception as e:
    logger.msg("ERROR","Exception: %s" % e)
    return None

# --- close database   -------------------------------------------------------

def close_db(options):
  """ close database """

  logger.msg("DEBUG","closing database")
  try:
    options.db.close()
    options.db = None
  except Exception as e:
    logger.msg("ERROR","Exception: %s" % e)

# --- execute a statement   -------------------------------------------------

def exec_sql(options,statement,args=(),commit=False):
  """ execute an sql-statement """

  logger.msg("DEBUG","executing: %s" % statement)
  try:
    open_db(options)
    cursor = options.db.cursor()
    cursor.execute(statement,args)
    if commit:
      options.db.commit()
    close_db(options)
  except sqlite3.OperationalError as oe:
    logger.msg("ERROR","SQL-error: %s" % oe)
  except Exception as e:
    logger.msg("ERROR","Exception: %s" % e)


# --- create the database   -------------------------------------------------

def do_create(options):
  """ create the database """
  logger.msg("INFO","creating database %s" % options.db_name)
  
  open_db(options)
  cursor = options.db.cursor()

  cursor.execute("DROP TABLE IF EXISTS schedule")
  cursor.execute("""CREATE TABLE schedule
      (owner text,
       label text,
       type  text,
       value text,
       state integer,
       time  text)""")
  close_db(options)

# --- add an uptime-entry to the database   ---------------------------------

def do_add(options):
  """ add an entry to the database """
  logger.msg("INFO","adding entry to the database")
  INSERT_STMT = 'INSERT INTO schedule VALUES (' + 5 * '?,' + '?)'

  # check if input is on the commandline or from stdin
  if options.args[0] == '-':
    # read from stdin
    for line in sys.stdin:
      if line[0] == '#':
        # ignore comments
        continue
      args = line.split()
      do_add_sql(options,args[:5])  # strip of extra stuff (e.g. comments)
    pass
  else:
    # use commandline arguments
    do_add_sql(options,options.args)

# --- add an uptime-entry to the database   ---------------------------------

def do_add_sql(options,sql_args):
  """ add an entry to the database """
  logger.msg("DEBUG","adding entry to the database")
  logger.msg("TRACE","sql_args: %r" % sql_args)
  INSERT_STMT = 'INSERT INTO schedule VALUES (' + 5 * '?,' + '?)'

  # split interval
  start,end = sql_args[4].split("-")
  if len(start) == 5:
    start = "%s:00" % start
  if len(end) == 5:
    end   = "%s:00" % end

  # convert date
  if sql_args[2] == 'DATE':
    sep = sql_args[3][2]
    parts=sql_args[3].split(sep)
    if len(parts[2]) == 2:
      parts[2] = "20%s" % parts[2]
    sql_args[3] = "%s-%s-%s" % (parts[2],parts[1],parts[0])

  # start of uptime-interval
  args=(sql_args[0],sql_args[1],sql_args[2],sql_args[3],1,start)
  exec_sql(options,INSERT_STMT,args=args,commit=True)

  # end of uptime-interval
  args=(sql_args[0],sql_args[1],sql_args[2],sql_args[3],0,end)
  exec_sql(options,INSERT_STMT,args=args,commit=True)

# --- delete an uptime-entry to the database   ------------------------------

def do_del(options):
  """ deleta entries in the database """
  logger.msg("INFO","deleting entries from the database")

  if len(options.args) == 0:
    logger.msg("ERROR", "missing argument for delete")
    sys.exit(3)  
  elif len(options.args) == 1:
    logger.msg("INFO", "deleting all entries for owner %s" % options.args[0])
    statement = "DELETE FROM schedule where owner=?"
  else:
    logger.msg("INFO", "deleting entries for owner,label=(%s,%s)" %
               (options.args[0],options.args[1]))
    statement = "DELETE FROM schedule where owner=? and label=?"

  exec_sql(options,statement,args=tuple(options.args),commit=True)

# --- list entries of the database   ----------------------------------------

def do_raw(options):
  """ list entries of the database """
  logger.msg("INFO","listing entries of the database")

  open_db(options)
  cursor = options.db.cursor()
  cursor.execute("select * from schedule")
  rows = cursor.fetchall()
  close_db(options)

  # print results
  print LIST_HEADER
  print LIST_SEP
  for row in rows:
    print LIST_FORMAT.format(*row)

# --- list uptimes for a given period   -------------------------------------

def do_list(options):
  """ list uptimes """

  list_type = options.args[0] if len(options.args) else 'today'
  logger.msg("INFO","listing uptimes for %s" % list_type)

  if list_type == 'today':
    rows = fetch_uptimes(options,datetime.date.today())
  elif list_type == 'week':
    delta = datetime.timedelta(1)
    day = datetime.date.today()
    rows = []
    for _ in range(7):
      rows.extend(fetch_uptimes(options,day))
      day = day + delta
  else:
    # list_type contains a date
    length = len(list_type)
    sep = list_type[2]
    parts = list_type.split(sep)
    list_type = "%s%s%s%s" % (parts[0],sep,parts[1],sep)
    print list_type
    if length == 8:
      list_type = list_type + "20" + parts[2]
    else:
      list_type = list_type + parts[2]
      print list_type
    rows = fetch_uptimes(options,datetime.datetime.strptime(list_type,"%x").date())

  # print results
  if rows:
    print LIST_HEADER
    print LIST_SEP
    for row in rows:
      print LIST_FORMAT.format(*row)

# --- list uptimes for a given date   ---------------------------------------

def fetch_uptimes(options,date):
  """ fetch uptimes for given date """
  logger.msg("DEBUG","fetching uptimes for %r" % date)

  # get entries in DB
  open_db(options)
  cursor = options.db.cursor()
  cursor.execute("""
     select * from schedule where
      type = 'DOW'  AND value=?  OR
      type = 'DOM'  AND value=?  OR
      type = 'DATE' AND value=?
         order by time, state desc""",(dow(date),dom(date),dates(date)))
  rows = cursor.fetchall()
  close_db(options)
  for row in rows:
    logger.msg("TRACE","%r" % (row,))
  return rows

# --- get next boot or halt time   ------------------------------------------

def do_get(options):
  """ get next boot or halt time """

  logger.msg("INFO","get next boot/halt time")

# --- activate next shutdown   ----------------------------------------------

def do_act(options):
  """ activate next shutdown """

  logger.msg("INFO","activating next shutdown")

# --- commandline parser   --------------------------------------------------

def get_parser():
  parser = argparse.ArgumentParser(add_help=False,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description='uptime-manager: manage uptimes of a system',
    epilog="""
Available commands:
  create: (re-) create the database
  add owner label DOW|DOM|DATE value start-end: add uptime period
  del owner [label]: delete all entries for owner or owner/label
  raw: list database (raw mode)
  list [today|week|<date>]: list consolidated uptimes
  get halt|boot: get next halt-time/boot-time
  act: schedule shutdown for next halt-time
  """)
  parser.add_argument('-D', '--db', metavar=('database',), required=True,
    dest='db_name', help='database-file')

  parser.add_argument('-q', '--quiet', default=False, action='store_true',
    dest='quiet',
    help='output no messages')
  parser.add_argument('-l', '--level', dest='level', default='INFO',
                      metavar='debug-level',
                      choices=['NONE','ERROR','WARN','INFO','DEBUG','TRACE'],
    help='debug level: one of NONE, ERROR, WARN, INFO, DEBUG, TRACE')
  parser.add_argument('--version', action='store_true',
    dest='do_version_info',
    help='print version info')
  parser.add_argument('-h', '--help', action='help',
    help='print this help')

  parser.add_argument('cmd',
                      choices=['create','add','del','raw','list','get','act'],
                      help='command to execute')
  parser.add_argument('args', nargs='*', metavar='argument',
    help='arguments for given command')
  return parser

# --- main program   --------------------------------------------------------

if __name__ == '__main__':
  locale.setlocale(locale.LC_ALL, '')

  opt_parser = get_parser()
  options = opt_parser.parse_args(namespace=Options)
  if options.do_version_info:
    print("version: %s" % VERSION)
    sys.exit(0)

  # configure message-class
  logger = Msg(options.level)

  func = globals()["do_%s" % options.cmd]
  func(options)
  sys.exit(0)

