# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

#
# A parser for logs as generated by DevStack's `stack.sh` script.
# Logs can be generated by running:
#     LOGFILE="output.log" ./stack.sh
#
# Two files will be generated:
#  - test.log.(datestamp): referred to as "log"
#  - test.log.(datestamp).summary.(datestamp): referred to as "summary"
#
# The full log can be parsed using `parse_log(path)` and the summary can be
# parsed using `parse_summary(path)`. Both functions will return a list of
# `LogNode` instances which can be combined and categorized using `merge()`.
#
# For testing purposes, it's recommended to use an IPython shell. Import this
# module, and call `bootstrap()` against the path to the primary logfile to get
# the fully merged list of `LogNode` instances. Nodes can be analyzed directly
# using the IPython `_repr_pretty_` functionality.
#

import os

from datetime import datetime
from datetime import timedelta
from log_node import LogNode

#: The format of the timestamp prefixing each log entry
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


def extract_date(line):
    """Extracts a date from the given line

    Returns the parsed date and remaining contents of the line.

    :param line: the line to extract a date from
    :return: a tuple of the parsed date and remaining line contents
    """

    date_str, message = line.split(' | ', 1)
    date = datetime.strptime(date_str, TIMESTAMP_FORMAT)

    return date, message.strip()


def parse_summary(summary_path):
    """Parses a summary logfile

    Summary entries are prefixed with identical datestamps to those in the
    main log, but have only explicit log messages denoting the overall
    execution progress.

    While summary entries are also printed into the main log, the explicit
    summary file is used to simplify parsing.

    :param summary_path: the path to the summary file to parse
    :return: a list of ordered `LogNode` instances
    """

    ret = []

    last_node = None

    with open(summary_path, 'r') as f:
        for line in f:
            date, message = extract_date(line)

            node = LogNode(date, message)
            if last_node:
                last_node.next_sibling = node

            ret.append(node)
            last_node = node

    return ret


def parse_log(log_path):
    """Parses a general `stack.sh` logfile, forming a full log tree

    The log tree is based on the hierarchy of nested commands as presented
    in the log.

    Note that command output (that is, lines not prefixed with one or more '+'
    symbols) is ignored and will not be included it the returned list of log
    nodes.

    :param log_path: the path to the logfile to parse
    :return: a list of parsed `LogNode` instances
    """

    last_depth = 1
    last_node = None

    # fake node to act as root stack entry
    ret = LogNode(None, None)

    node_stack = [ret]

    with open(log_path, 'r') as f:
        for line in f:
            date, message = extract_date(line)

            if not message.startswith('+'):
                # ignore command output - we only want actual commands
                continue

            depth = 0
            for char in message:
                if char == '+':
                    depth += 1
                else:
                    break

            if depth - last_depth > 1:
                # skip discontinuous lines (???)
                continue

            # adjust the stack if the depth has changed since the last node
            if depth < last_depth:
                node_stack.pop()
            elif depth > last_depth:
                node_stack.append(last_node)

            node = LogNode(date, message.lstrip('+ '))

            parent = node_stack[-1]
            parent.children.append(node)

            if last_node:
                last_node.next_sibling = node

            last_depth = depth
            last_node = node

    return ret.children


def merge(summary, log):
    """Merges log entries into parent categories based on timestamp.

    Merges general log entries into parent categories based on their timestamp
    relative to the summary output timestamp.

    Note that this function is destructive and will directly modify the nodes
    within the `summary` list.

    :type summary: list[LogNode]
    :param summary: the list of summary nodes
    :type log: list[LogNode]
    :param log: the list of general log nodes
    :return: the original summary nodes with children set to the log nodes
    """

    if not summary:
        return []

    current_node = summary[0]
    next_node = current_node.next_sibling

    for i, entry in enumerate(log):
        if entry.date < current_node.date:
            # skip forward until a possible summary node is reached
            continue

        if entry.date < next_node.date:
            current_node.children.append(entry)
        else:
            next_node.children.append(entry)

            current_node = next_node
            next_node = current_node.next_sibling

    return summary


def bootstrap(log_path, summary_path=None):
    """Loads, parses, and merges the given log and summary files.

    The path to the summary file will be determined automatically based on the
    path to the general logfile, but it must exist within the same directory.

    If the log file names are changed from their default values, a summary path
    can be explicitly provided using the optional `summary_path` parameter.

    :param log_path: the path to the logfile to parse
    :param summary_path: optional; bypasses autodetection of path names
    :return: a list of merged `LogNode` instances, or `None` if no matching
             summary file can be located automatically
    """

    if summary_path:
        return merge(parse_summary(summary_path), parse_log(log_path))

    name = os.path.basename(log_path)
    directory = os.path.dirname(os.path.abspath(log_path))

    for candidate in os.listdir(directory):
        if candidate.startswith('{0}.summary.'.format(name)):
            return merge(parse_summary(os.path.join(directory, candidate)),
                         parse_log(os.path.join(directory, name)))

    return None


def get_command_totals(node, totals=None):
    if totals is None:
        totals = {}

    for entry in node.traverse():
        # attempt to resolve a nice looking command, ignoring any obvious
        # arguments to make subcommands float to left of array
        tokens = filter(lambda tok: not tok.startswith('-'),
                        entry.message.split())
        if not tokens:
            continue

        # strip sudo and any variable declarations
        if tokens[0] == 'sudo':
            tokens.pop(0)

            while '=' in tokens[0]:
                tokens.pop(0)

        if '/' in tokens[0]:
            tokens[0] = tokens[0].split('/')[-1]

        # select # of tokens to include based on the first token
        token_count = {
            'openstack': 2,
            'read': 2,
            'python': 2
        }.get(tokens[0], 1)

        # combine token_count tokens to generate the command to group by
        combined = ' '.join(tokens[0:token_count])
        if combined not in totals:
            totals[combined] = timedelta()

        totals[combined] += entry.duration_self

    return totals
