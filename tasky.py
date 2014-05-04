#!/usr/bin/env python2
"""
A Google Tasks command line interface.
Author: Ajay Roopakalu (https://github.com/jrupac/tasky)

Fork: Conner McDaniel (https://github.com/connermcd/tasky)
        - Website: connermcd.com
        - Email: connermcd using gmail
"""

# TODO:
#  * error catching
#  * make code cleaner/better

from __future__ import print_function

from apiclient.discovery import build
from argparse import ArgumentParser
from collections import OrderedDict
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage
from oauth2client.tools import run

import datetime as dt
import httplib2
import os
import sys
import time
# import json # TODO


def remove_task(listIndex, task):
    tasklist = TaskLists[TaskLists.keys()[listIndex]]

    # If already deleted, do nothing
    if task['modified'] is DELETED:
        return
    task['modified'] = DELETED
    del IDToTitle[task['id']]

    # Also delete all children of deleted tasks
    for taskID in tasklist:
        t = tasklist[taskID]
        if ('parent' in t and 
                t['parent'] in tasklist and 
                tasklist[t['parent']]['modified'] is DELETED):
            t['modified'] = DELETED
            if t['id'] in IDToTitle:
                del IDToTitle[t['id']]

def toggle_task(listIndex, task):
    tasklist = TaskLists[TaskLists.keys()[listIndex]]

    if task['modified'] is DELETED:
        return
    task['modified'] = MODIFIED

    if task['status'] == 'needsAction':
        task['status'] = 'completed'
    else:
        task['status'] = 'needsAction'
        if 'completed' in task:
            del task['completed']

    # Also toggle all children whose parents were toggled
    toggle_tree = [task['id']]
    for taskID in tasklist:
        t = tasklist[taskID]
        if t['status'] is DELETED:
            continue
        if 'parent' in t and t['parent'] in toggle_tree:
            t['status'] = tasklist[t['parent']]['status']
            if t['status'] == 'needsAction' and 'completed' in t:
                del t['completed']
            toggle_tree.append(t['id'])
            t['modified'] = MODIFIED
            tasklist[t['id']] = t

def get_data():
    global TaskLists
    # Only retrieve data once per run
    if TaskLists != {}:
        return

    # Fetch task lists
    tasklists = service.tasklists().list().execute()

    # No task lists
    if 'items' not in tasklists:
        return

    # Over all task lists
    for tasklist in tasklists['items']:
        # Handle repeats
        if tasklist['title'] in IDToTitle:
            continue
        IDToTitle[tasklist['id']] = tasklist['title']
        TaskLists[tasklist['id']] = OrderedDict()
        tasks = service.tasks().list(tasklist = tasklist['id']).execute()
        # No task in current list
        if 'items' not in tasks:
            continue
        # Over all tasks in a given list
        for task in tasks['items']:
            IDToTitle[task['id']] = task['title']
            # Set everything to be initially unmodified
            task['modified'] = UNCHANGED
            TaskLists[tasklist['id']][task['id']] = task

def put_data():
    # Nothing to write home about
    if TaskLists == {}:
        return

    for tasklistID in TaskLists:
        for taskID in TaskLists[tasklistID]:
            task = TaskLists[tasklistID][taskID]
            if task['modified'] is UNCHANGED:
                continue
            elif task['modified'] is MODIFIED:
                service.tasks().update(
                        tasklist = tasklistID,
                        task = taskID,
                        body = task,
                        ).execute()
            elif task['modified'] is DELETED:
                service.tasks().delete(
                        tasklist = tasklistID,
                        task = taskID,
                        ).execute()

def print_all_tasks(tasklistID):
    tab = '  '

    # No task lists
    if TaskLists == {}:
        print('Found no task lists.')
        return

    # print(json.dumps(TaskLists, indent=4)) TODO

    # Use a dictionary to store the indent depth of each task
    depthMap = { tasklistID : 0 }
    depth = 1

    # Print task name
    if len(TaskLists[tasklistID]) == 0:
        print(IDToTitle[tasklistID], '(empty)')
    else:
        print(IDToTitle[tasklistID])

    for taskID in TaskLists[tasklistID]:
        task = TaskLists[tasklistID][taskID]
        if task['modified'] is DELETED:
            continue
        depth = 1
        isCompleted = (task['status'] == 'completed')

        # Set the depth of the current task
        if 'parent' in task and task['parent'] in depthMap:
            depth = depthMap[task['parent']] + 1
        depthMap[task['id']] = depth

        # Print x in box if task has already been completed
        if isCompleted:
            print(tab * depth,
                    TaskLists[tasklistID].keys().index(taskID),
                    '[x]',
                    task['title'])
                    #task['position'], # TODO
        else:
            print(tab * depth,
                    TaskLists[tasklistID].keys().index(taskID),
                    '[ ]',
                    task['title'])
                    #task['position'] # TODO

        # Print due date if specified
        if 'due' in task:
            date = dt.datetime.strptime(task['due'],
                    '%Y-%m-%dT%H:%M:%S.%fZ')
            output = date.strftime('%a, %b %d, %Y')
            print(tab * (depth + 1),
                    'Due Date: {0}'.format(output))

        # Print notes if specified
        if 'notes' in task:
            print(tab * (depth + 1),
                    'Notes: {0}'.format(task['notes']))

def print_summary():
    for tasklistID in TaskLists:
        print(TaskLists.keys().index(tasklistID),
                IDToTitle[tasklistID],
                '(', len(TaskLists[tasklistID]), ')')

def handle_input_args(args, atasklistID=0):
    args['list'] = int(args['list'])
    if atasklistID == 0:
        atasklistID = args['list']
    tasklistID = TaskLists.keys()[atasklistID]
    tasklist = TaskLists[tasklistID]

    if action is 'a':
        for title in args['title']:
            task = { 'title' : ''.join(title) }
            if args['date'] is not None:
                dstr = ''.join(args['date'])
                d = time.strptime(dstr, "%m/%d/%y")
                task['due'] = (
                        str(d.tm_year) + '-' + 
                        str(d.tm_mon) + '-' + 
                        str(d.tm_mday) + 
                        'T12:00:00.000Z')
            if args['note'] is not None:
                task['notes'] = ''.join(args['note'])
            if args['parent'] is not None:
                task['parent'] = int(args['parent'][0])
            print('Adding task...')
            add_task(atasklistID, task)
    if action is 'd':
        readIn = raw_input('This will delete the list "' + 
                IDToTitle[tasklistID] + 
                '" and all its contents permanently. Are you sure? (y/n) ')
        if readIn is 'Y' or readIn is 'y':
            service.tasklists().delete(tasklist = tasklistID).execute()
        del TaskLists[tasklistID]
        print_summary()
        put_data()
        sys.exit(True)
    if action is 'n':
        if args['rename'] is True:
            print('Renaming task list...')
            tasklist = service.tasklists().get(
                    tasklist = tasklistID,
                    ).execute()
            tasklist['title'] = args['title'][0]
            IDToTitle[tasklistID] = args['title'][0]
            service.tasklists().update(
                    tasklist = tasklistID,
                    body = tasklist,
                    ).execute()
            time.sleep(3)
        else:
            print('Creating new task list...')
            newTaskList = service.tasklists().insert(
                    body = {'title': args['title']},
                    ).execute()
            IDToTitle[newTaskList['id']] = newTaskList['title']
            TaskLists[newTaskList['id']] = OrderedDict()
        print_summary()
        put_data()
        sys.exit(True)
    elif tasklist == {}:
        print(IDToTitle[tasklistID], '(empty)')
        return
    elif action is 'e':
        print('Editing task...')
        task = tasklist[tasklist.keys()[int(args['index'][0])]]
        if args['title'] is not None:
            task['title'] = ''.join(args['title'])
        if args['date'] is not None:
            dstr = ''.join(args['date'])
            d = time.strptime(dstr, "%m/%d/%y")
            task['due'] = (str(d.tm_year) + '-' +
                    str(d.tm_mon) + '-' + 
                    str(d.tm_mday) + 
                    'T12:00:00.000Z')
        if args['note'] is not None:
            task['notes'] = ''.join(args['note'])
        if task['modified'] == DELETED:
            return
        task['modified'] = MODIFIED
    elif action is 'm':
        print('Moving task...')
        task = tasklist[tasklist.keys()[int(args['index'][0])]]
        move_task(atasklistID, task, args)
        put_data()
        sys.exit(True)
    elif action is 'c':
        if args['all'] is True:
            print('Removing all tasks...')
            for taskID in tasklist:
                remove_task(atasklistID, tasklist[taskID])
        else:
            print('Clearing completed tasks...')
            service.tasks().clear(tasklist = tasklistID).execute()
            for taskID in tasklist:
                task = tasklist[taskID]
                if task['status'] == 'completed':
                    task['modified'] = DELETED
    elif action is 'r':
        print('Removing task...')
        for index in args['index']:
            index = int(index)
            remove_task(atasklistID, tasklist[tasklist.keys()[index]])
    elif action is 't':
        print('Toggling task...')
        for index in args['index']:
            index = int(index)
            toggle_task(atasklistID, tasklist[tasklist.keys()[index]])

    if action is 'l' and args['all'] is True:
        for tasklistID in TaskLists:
            print_all_tasks(tasklistID)
    elif action is 'l' and args['summary'] is True:
        print_summary()
    else:
        print_all_tasks(tasklistID)

def parse_arguments(args):
    # TODO move alias to config file (YAML?)
    alias = {
            'a': 'add',
            'c': 'clear',
            'd': 'delete',
            'e': 'edit',
            'r': 'remove',
            'rm': 'remove',
            'l': 'list',
            'ls': 'list',
            'm': 'move',
            'n': 'new',
            't': 'toggle',
            'q': 'quit',
            'exit': 'quit',
            }
    args[0] = alias.get(args[0], args[0])

    parser = ArgumentParser(description = "A Google Tasks Client.
    Type tasky <argument> -h for more detailed information.")

    subparsers = parser.add_subparsers(dest = 'subcommand')
    parser.add_argument('-l', '--list',
            default = 0,
            help = 'Specifies task list (default: 0)')

    parser_add = subparsers.add_parser('add')
    parser_add.add_argument('title', nargs = '*',
            help = 'The name of the task.')
    parser_add.add_argument('-d', '--date', nargs = 1,
            help = 'A date in MM/DD/YYYY format.')
    parser_add.add_argument('-n', '--note', nargs = 1,
            help = 'Any quotation-enclosed string.')
    parser_add.add_argument('-p', '--parent', nargs = 1,
            help = 'The id of the parent task.')

    parser_edit = subparsers.add_parser('edit')
    parser_edit.add_argument('index', nargs = 1,
            help = 'Index of the task to edit.')
    parser_edit.add_argument('-t', '--title', nargs = 1,
            help = 'The new title after editing.')
    parser_edit.add_argument('-d', '--date', nargs = 1,
            help = 'A new date in MM/DD/YYYY format.')
    parser_edit.add_argument('-n', '--note', nargs = 1,
            help = 'The new note after editing.')

    parser_move = subparsers.add_parser('move')
    parser_move.add_argument('index', nargs = 1,
            help = 'Index of the task to move.')
    parser_move.add_argument('-a', '--after', 
            nargs = 1, default = -1,
            help = 'Move the task after this index. (default: -1)')
    parser_move.add_argument('-p', '--parent',
            nargs = 1,
            help = 'Make the task a child of this index.')

    parser_clear = subparsers.add_parser('clear')
    parser_clear.add_argument('-a', '--all',
            action='store_true',
            help = 'Remove all tasks, completed or not.')

    subparsers.add_parser('delete')

    parser_new = subparsers.add_parser('new')
    parser_new.add_argument('title', nargs='*',
            help = 'The name of the new task list.')
    parser_new.add_argument('-r', '--rename', action='store_true',
            help = 'Set if renaming an already existing task list.')

    parser_list = subparsers.add_parser('list')
    parser_list.add_argument('-a', '--all', action='store_true',
            help = 'Print all tasks in all task lists.')
    parser_list.add_argument('-s', '--summary', action='store_true',
            help = 'Print a summary of available task lists.')

    parser_remove = subparsers.add_parser('remove')
    parser_remove.add_argument('index', nargs = '*',
            help = 'Index of the task to remove.')

    parser_toggle = subparsers.add_parser('toggle')
    parser_toggle.add_argument('index', nargs = '*',
            help = 'Index of the task to toggle.')

    # TODO
    # run func provided by subparser
    # return t.get_name(t.current_tasklist_id)

    print(vars(parser.parse_args(args)))
    return parser.parse_args(args)

class Tasks():
    def __init__(self):
        #TODO self._configure()
        self.conf = {'keyfile': '~/.tasky/dev_keys',
                'confdir': '~/.tasky',
                }
        self._authenticate()

    def _authenticate(self):
        # If credentials don't exist or are invalid, run through the native client
        # flow. The Storage object will ensure that if successful the good
        # Credentials will get written back to a file.
        storage = Storage(os.path.join(self.conf['confdir'], 'token'))
        credentials = storage.get()

        if credentials is None or credentials.invalid:
            # try to get dev keys on file
            try:
                with open(self.conf['keyfile'], 'r') as keyfile:
                    client_id = keyfile.readline()
                    client_secret = keyfile.readline()
                    api_key = keyfile.readline()
            except IOError:
                # File doesn't exist, so prompt for them
                # and then create the file
                print("Google credentials not found")
                client_id = raw_input("Enter your clientID: ")
                client_secret = raw_input("Enter your client secret: ")
                api_key = raw_input("Enter your API key: ")

                if not os.path.exists(self.conf['confdir']):
                    os.makedirs(self.conf['confdir'])
                with open(self.conf['keyfile'], 'w') as keyfile:
                    keyfile.write(str(client_id) + '\n')
                    keyfile.write(str(client_secret) + '\n')
                    keyfile.write(str(api_key) + '\n')

            # OAuth 2.0 Authentication
            FLOW = OAuth2WebServerFlow(
                client_id=client_id,
                client_secret=client_secret,
                scope='https://www.googleapis.com/auth/tasks',
                user_agent='Tasky/v1')

            credentials = run(FLOW, storage)

        http = httplib2.Http()
        http = credentials.authorize(http)

        # The main Tasks API object
        self.api = build(serviceName='tasks', 
                version='v1',
                http=http,
                developerKey=api_key)

    def add(self, **kargs):
        #TODO allow change tasklist

        # self.tasklists should be an ordered dict with
        # google id's as keys
        current_tasklist = self.taskslists[self.current_tasklist_id]

        new_task = {'tasklist': self.current_tasklist_id,
                'title': kargs['title'],
                }

        if 'due' in kargs:
            #TODO take any date format
            d = time.strptime(kargs['due'], "%m/%d/%y")
            #TODO use datetime libs to do this
            new_task['due'] = (
                    str(d.tm_year) + '-' + 
                    str(d.tm_mon) + '-' + 
                    str(d.tm_mday) + 
                    'T12:00:00.000Z')

        if 'note' in kargs:
            new_task['notes'] = kargs['note']

        if 'parent' in kargs:
            # TODO: try:
            # task['parent'] = int(arg.parent)
            # except:
            # task['parent'] = self.get_list_id(args.parent)
            parent_int = int(kargs['parent'])
            parent_id = current_tasklist.keys()[parent_int]
            new_task['parent'] = parent_id

        reply = self.api.tasks().insert(**new_task).execute()

        # Re-insert the new task in order
        new_tasklist = OrderedDict()
        for t in current_tasklist:
            new_tasklist[t] = current_tasklist[t]
            if t['id'] == parent_id:
                new_tasklist[reply['id']] = reply

        # Update records
        self.tasklists[self.current_tasklist_id] = new_tasklist

    def move(self, **kargs):
        # TODO allow moving to different tasklist

        current_tasklist = self.taskslists[self.current_tasklist_id]
        task_id = current_tasklist.keys()[int(kargs.get('task', 0))]
        api_args = {'tasklist': self.current_tasklist_id,
                'task': task_id,
                }

        # TODO allow many ways to spec position
        pos = int(kargs.get('pos', 0))
        parent = int(kargs.get('parent', 0))

        if pos:
            api_args['previous'] = current_tasklist.keys()[pos-1]

        if parent:
            api_args['parent'] = current_tasklist.keys()[parent]

        newTask = service.tasks().move(**api_args).execute()
        # del TaskLists[tasklistIndex][task['id']]
        # tasklist[newTask['id']] = newTask
        # IDToTitle[newTask['id']] = newTask['title']
        # newTask['modified'] = UNCHANGED

def interactiveLoop():
    while True:
        readIn = raw_input("tasks> ")
        args = readIn.split()
        args = parse_arguments(args)
        handle_input_args(args)


if __name__ == '__main__':
    authenticate()
    get_data()

    import atexit
    atexit.register(put_data)

    if len(sys.argv) == 1:
        interactiveLoop()
    else:
        args = parse_arguments(sys.argv[1:])
        handle_input_args(args)
