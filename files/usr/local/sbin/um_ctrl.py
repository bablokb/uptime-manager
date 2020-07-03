#!/usr/bin/python3
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

VERSION=1             # increase with incompatible changes

TIME_HORIZON =  7     # we peek at most 7 days into the future

# list formatting
LIST_HEADER = "Date       |Time      |Owner    | Label                | Type | Value      | State |"
LIST_SEP    = "-----------|----------|---------|----------------------|------|------------|-------|"
LIST_FORMAT = "{0:10} | {6:8} |{1:8} | {2:20} | {3:4} | {4:10} | {5:5} |"

RAW_HEADER = "Owner    | Label                | Type | Value      | State | Time     | id"
RAW_SEP    = "---------|----------------------|------|------------|-------|----------|---------------------"
RAW_FORMAT = "{0:8} | {1:20} | {2:4} | {3:10} | {4:5d} | {5:8} | {6:20d}"

STATE_HEADER = "Date       |Time      | State"
STATE_SEP    = "-----------|----------|------"
STATE_FORMAT = "{0:10} | {1:8} | {2:4}"

# tuple-index for rows retrieved
TYPE_INDEX    = 3
VALUE_INDEX   = 4
STATE_INDEX   = 5
STATE_INDEX_S = 2
I_TIME  = 6
I_DATE  = 0


# --- system-imports   -----------------------------------------------------

import argparse
import sys, os, datetime, sqlite3, locale, json, hashlib

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
    """ print message """
    if Msg.MSG_LEVELS[msg_level] >= Msg.MSG_LEVELS[self._level]:
      if nl:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sys.stderr.write("[" + msg_level + "] " + "[" + now + "] " + text + "\n")
      else:
        sys.stderr.write(text)
        sys.stderr.flush()

  # --- check level   -------------------------------------------------------

  def is_level(self,msg_level):
    """ return True if msg_level is at least self._level """
    return Msg.MSG_LEVELS[msg_level] >= Msg.MSG_LEVELS[self._level]

# ---------------------------------------------------------------------------

# --- isoweekday of given date   --------------------------------------------

def dow(date):
  """ return isoweekday of given date """

  return date.isoweekday()

# --- localized day-of-week map   -------------------------------------------

def dow_map():
  """ return localized day-of-week map """

  result = {}
  day   = datetime.datetime.strptime("01.01.2000","%d.%M.%Y")
  delta = datetime.timedelta(days=1)
  for _ in range(7):
    result[str(dow(day))] = day.strftime("%A")
    day = day + delta
  return result

# day-of-week text

# --- day of month of given date   ------------------------------------------

def dom(date):
  """ return day of given date """

  return date.day

# --- convert date to sql-date   --------------------------------------------

def date2sql(date):
  """ return sql-date of given date """

  return date.strftime("%Y-%m-%d")

# --- convert sql-date to date   --------------------------------------------

def sql2date(date):
  """ return date of given sql-date """

  return date.strptime(date,"%Y-%m-%d")

# --- convert sql-date and time to datetime   ------------------------------

def sql2datetime(date,time):
  """ return date of given sql-date """

  return datetime.datetime.strptime("%s %s" % (date,time), "%Y-%m-%d %H:%M:%S")

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
  logger.msg("DEBUG","args: %r" % (args,))
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
       time  text,
       id integer)""")
  close_db(options)

# --- add an uptime-entry to the database   ---------------------------------

def do_add(options):
  """ add an entry to the database

      format of the arguments:
        owner label type value start-end

      type is one of DOW/DOM/DATE

      DOW = Day-of-Week:  1-7 Monday-Sunday
      DOM = Day-of-Month: 1-31
  """

  # check if input is on the commandline or from stdin
  if options.args[0] == '-':
    logger.msg("INFO","add: parsing new entries from stdin")
    # read from stdin
    for line in sys.stdin:
      if line[0] == '#':
        # ignore comments
        continue
      args = line.split()[:5]     # strip of extra stuff (e.g. comments)
      do_add_sql(options,args)
  else:
    # use commandline arguments
    logger.msg("INFO","add: parsing new entries from the commandline")
    do_add_sql(options,options.args)

# --- add an uptime-entry to the database   ---------------------------------

def do_add_sql(options,sql_args):
  """ add an entry to the database """
  logger.msg("DEBUG","adding entry to the database")

  # calculate id of arguments
  sql_args[2] = sql_args[2].upper()
  id = int(hashlib.sha256(''.join(sql_args).encode('utf-8')).
           hexdigest()[:16],16)-2**63

  logger.msg("TRACE","sql_args: %r" % sql_args)
  PRE_INSERT_STMT = 'DELETE FROM schedule where id=?'
  INSERT_STMT     = 'INSERT INTO schedule VALUES (' + 6 * '?,' + '?)'

  # split interval
  start,end = sql_args[4].split("-")
  # add seconds if not specified
  if len(start) == 5:
    start = "%s:00" % start
  if len(end) == 5:
    end   = "%s:00" % end

  # convert date
  dtype = sql_args[2]
  if dtype == 'DATE':
    sep = sql_args[3][2]
    parts=sql_args[3].split(sep)
    if len(parts[2]) == 2:
      parts[2] = "20%s" % parts[2]
    value = "%s-%s-%s" % (parts[2],parts[1],parts[0])
  else:
    value = sql_args[3]

  # check if time-span overlapps midnight. Split if necessary
  if end < start:
    start2 = '00:00:00'
    end2   = end
    end    = '23:59:59'
    value2 = next_day(dtype,value)  # next value of given dtype
  else:
    start2 = None

  # remove old entries with given id
  exec_sql(options,PRE_INSERT_STMT,args=(id,),commit=True)

  # start of uptime-interval
  args=(sql_args[0],sql_args[1],dtype,value,1,start,id)
  exec_sql(options,INSERT_STMT,args=args,commit=True)

  # end of uptime-interval
  args=(sql_args[0],sql_args[1],dtype,value,0,end,id)
  exec_sql(options,INSERT_STMT,args=args,commit=True)

  # add second interval if necessary
  if start2:
    args=(sql_args[0],sql_args[1],dtype,value2,1,start2,id)
    exec_sql(options,INSERT_STMT,args=args,commit=True)
    args=(sql_args[0],sql_args[1],dtype,value2,0,end2,id)
    exec_sql(options,INSERT_STMT,args=args,commit=True)

# --- get next day of given dtype   -----------------------------------------

def next_day(dtype,value):
  """ value of next day, either a weekday name or a date """

  if dtype == 'DOW':
    return value % 7 + 1
  elif dtype == 'DOM':
    return value % 31 + 1
  else:
    value  = sql2datetime(value,"00:00:00")
    value += datetime.timedelta(1)
    return   date2sql(value)

# --- format value   --------------------------------------------------------

def format_value(vtype,value):
  """ return formatted value """

  if vtype == 'DOW':
    return DOW['value']
  else:
    return value

# --- print results   -------------------------------------------------------

def print_results(options,rows,state_only=False):
  """ pretty-print results """
  if state_only:
    if rows:
      print(STATE_HEADER)
      print(STATE_SEP)
      for row in rows:
        row = list(row)
        row[STATE_INDEX_S] = options.STATE_VALUES[row[STATE_INDEX_S]]
        print(STATE_FORMAT.format(*row))
  else:
    if rows:
      print(LIST_HEADER)
      print(LIST_SEP)
      for row in rows:
        row = list(row)
        if row[TYPE_INDEX] == 'DOW':
          row[VALUE_INDEX] = options.DOW[row[VALUE_INDEX]]
        row[STATE_INDEX] = options.STATE_VALUES[row[STATE_INDEX]]
        print(LIST_FORMAT.format(*row))

# --- delete an uptime-entry to the database   ------------------------------

def do_del(options):
  """ deleta entries in the database """
  logger.msg("INFO","deleting entries from the database")

  if len(options.args) == 0:
    logger.msg("ERROR", "missing argument for delete")
    sys.exit(3)  
  elif len(options.args) == 1:
    try:
      options.args[0] = int(options.args[0])
      logger.msg("INFO", "deleting all entries for id %d" % options.args[0])
      statement = "DELETE FROM schedule where id=?"
    except:
      logger.msg("INFO", "deleting all entries for owner %s" % options.args[0])
      statement = "DELETE FROM schedule where owner=?"
  else:
    logger.msg("INFO", "deleting entries for owner,label=(%s,%s)" %
               (options.args[0],options.args[1]))
    statement = "DELETE FROM schedule where owner=? and label=?"

  exec_sql(options,statement,args=options.args,commit=True)

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
  print(RAW_HEADER)
  print(RAW_SEP)
  for row in rows:
    print(RAW_FORMAT.format(*row))

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
    if length == 8:
      list_type = list_type + "20" + parts[2]
    else:
      list_type = list_type + parts[2]
    rows = fetch_uptimes(options,datetime.datetime.strptime(list_type,"%x").date())

  # print results
  print_results(options,rows)

# --- query uptimes for a given date   ---------------------------------------

def fetch_uptimes(options,date):
  """ fetch uptimes for given date """
  logger.msg("DEBUG","fetching uptimes for %r" % date)

  # get entries in DB
  open_db(options)
  cursor = options.db.cursor()
  cursor.execute("""
     select '%s',* from schedule where
      type = 'DOW'  AND value=?  OR
      type = 'DOM'  AND value=?  OR
      type = 'DATE' AND value=?
         order by time, state desc""" % date2sql(date),
                 (dow(date),dom(date),date2sql(date)))
  rows = cursor.fetchall()
  close_db(options)
  for row in rows:
    logger.msg("TRACE","%r" % (row,))
  return rows

# --- get next boot or halt time   ------------------------------------------

def do_get(options):
  """ get next boot or halt time """

  get_type = options.args[0] if len(options.args) else 'halt'
  logger.msg("INFO","calculating next %s" % get_type)
  today = date2sql(datetime.date.today())
  now   = datetime.datetime.now().time().strftime("%H:%M:%S")
  logger.msg("TRACE","now: %s" % now)

  states = consolidate_uptimes(options,raw=get_type=='raw')
  if get_type in ['raw','all']:
    print_results(options,states,True)
    return ""

  for (day,time,state) in states:
    if day > today:
      now = "00:00:00"
    if get_type == "boot" and state == 0:
      continue
    elif get_type == "halt" and state == 1:
      continue
    elif now <= time:
      # convert to datetime and add grace-periods
      dt_time = datetime.datetime.strptime("%s %s" % (day,time),"%Y-%m-%d %H:%M:%S")
      if get_type == "boot":
        delta = datetime.timedelta(minutes=-options.grace_boot)
      elif get_type == "halt":
        delta = datetime.timedelta(minutes=options.grace_halt)
      dt_time += delta
      str_time = datetime.datetime.strftime(dt_time,"%Y-%m-%d %H:%M:%S")
      if options.cmd == 'get':
        print(str_time)
      else:
        return str_time,dt_time
      return

  return ""

# --- set next halt|boot time   ---------------------------------------------

def do_set(options):
  """ set next boot or halt time
      This method will call um_set_boot/um_set_halt and pass four values:
        - action-time as %Y-%m-%d %H:%M:%S
        - action-time as %s (unix-timestamp aka seconds since epoch)
        - time in seconds until action-time
        - path to database
  """

  if len(options.args) != 1:
    print("the set command needs a single option halt|boot")
    return

  set_type = options.args[0]
  if set_type not in ['halt','boot']:
    print("the set command needs a single option halt|boot")
    return

  t_action,dt_action = do_get(options)
  dt_now    = datetime.datetime.now()
  delta     = dt_action - dt_now
  logger.msg("INFO","setting next %s at %s" % (set_type,t_action))
  hook = os.path.join(options.pgmdir,"um_set_%s" % set_type)
  os.system("%s \"%s\" %d %d \"%s\" &" %
            (hook,t_action,dt_action.timestamp(),
             delta.total_seconds(),options.db_name))

# --- consolidate uptimes   --------------------------------------------------

def consolidate_uptimes(options,raw=False):
  """ consolidate uptime """

  # we might have to look into the future, so we iterate starting from today
  delta = datetime.timedelta(1)
  day   = datetime.date.today()
  now   = datetime.datetime.now().strftime("%H:%M:%S")

  result = []
  state = 0
  logger.msg("TRACE","state: %d" % state)

  # we first aggregate all uptime periods
  for i in range(TIME_HORIZON):
    logger.msg("TRACE","examining day %s" % date2sql(day))
    first_boot = i == 0
    rows = fetch_uptimes(options,day)
    for row in rows:
      # aggregate uptime-requests
      if row[STATE_INDEX] == 1:
        state += 1
      else:
        state = max(state-1,0)
      logger.msg("TRACE","time: %s, state: %d" % (row[I_TIME],state))

      # next halt is when we reach zero
      if (state == 0):
        logger.msg("TRACE","adding time: %s, state: %d" % (row[I_TIME],state))
        result.append((date2sql(day),row[I_TIME],state))
      # next boot is after a transition from 0 to 1
      elif (state == 1 and row[STATE_INDEX] == 1):
        logger.msg("TRACE","adding time: %s, state: %d" % (row[I_TIME],state))
        result.append((date2sql(day),row[I_TIME],state))
      elif (state > 1 and row[STATE_INDEX] == 1
            and first_boot and row[I_TIME] > now):
        logger.msg("TRACE","adding time: %s, state: %d" % (row[I_TIME],state))
        result.append((date2sql(day),row[I_TIME],1))
        first_boot = False
    # at this stage we have to peek into the next day
    day = day + delta

  # for debug-purposes, print list
  if logger.is_level("DEBUG"):
    logger.msg("DEBUG","state-changes before consolidation: %d" % len(result))
    print_results(options,result,True)

  # finish here, if raw values were requested
  if raw:
    return result

  # now we consolidate the periods
  delta = datetime.timedelta(minutes=options.min_downtime)
  i = 0
  day = datetime.date.today().strftime("%Y-%m-%d")
  while True and len(result):
    if i >= len(result)-1:
      break
    (day_c,time_c,state_c) = result[i]
    logger.msg("TRACE","examining: %s,%s,%d" % (day_c,time_c,state_c))
    if day_c == day and time_c < now:
      # skip events in the past
      del result[i]    # deletes current entry
      continue
    if state_c:
      # never remove an up-event
      i += 1
      continue
    (day_n,time_n,state_n) = result[i+1]
    dt_c = sql2datetime(day_c,time_c)
    dt_n = sql2datetime(day_n,time_n)
    if (dt_c + delta > dt_n):
      logger.msg("TRACE","deleting %r" % (result[i],))
      del result[i]    # deletes current down
      logger.msg("TRACE","deleting %r" % (result[i],))
      del result[i]    # deletes next up
    else:
      # skip to next down
      i += 2

  # for debug-purposes, print list
  if logger.is_level("DEBUG"):
    logger.msg("DEBUG","state-changes after consolidation: %d" % len(result))
    print_results(options,result,True)

  return result

# --- read settings   ------------------------------------------------------

def read_settings(options):
  """ read settings from /etc/uptime-manager.json """

  sname = "/etc/uptime-manager.json"
  if os.path.exists(sname):
    logger.msg("INFO","reading settings from %s" % sname)
    with open(sname,"r") as f:
      settings = json.load(f)
  else:
    settings = {}

  if "grace_boot" in settings:
    options.grace_boot = settings["grace_boot"]
  else:
    options.grace_boot = 3
  if "grace_halt" in settings:
    options.grace_halt = settings["grace_halt"]
  else:
    options.grace_halt = 3
  if "min_downtime" in settings:
    options.min_downtime = settings["min_downtime"]
  else:
    options.min_downtime = 10

# --- commandline parser   --------------------------------------------------

def get_parser():
  parser = argparse.ArgumentParser(add_help=False,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description='uptime-manager: manage uptimes of a system',
    epilog="""
Available commands:
  create:                                       (re-) create the database
  add owner label DOW|DOM|DATE value start-end: add uptime period
  del id | owner [label]:                       delete all entries for id or owner or owner/label
  raw:                                          list database (raw mode)
  list [today|week|<date>]:                     list all uptimes (unconsolidated)
  get halt|boot|all|raw:                        get (next) halt-time/boot-time
  set halt|boot:                                set next halt-time|boot-time (call um_set_halt|um_set_boot)
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
                      choices=['create','add','del','raw','list','get','set'],
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
  else:
    options.pgmdir = os.path.dirname(sys.argv[0])
    options.DOW = dow_map()                         # map isoweekday to string
    options.STATE_VALUES = ['down','up']

  # configure message-class
  logger = Msg(options.level)

  # read settings
  read_settings(options)

  # execute command and exit
  func = globals()["do_%s" % options.cmd]
  func(options)
  sys.exit(0)

