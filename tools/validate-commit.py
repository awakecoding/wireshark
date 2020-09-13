#!/usr/bin/env python
# Verifies whether commit messages adhere to the standards.
# Checks the author name and email and invokes the tools/commit-msg script.
# Copy this into .git/hooks/post-commit
#
# Copyright (c) 2018 Peter Wu <peter@lekensteyn.nl>
#
# Wireshark - Network traffic analyzer
# By Gerald Combs <gerald@wireshark.org>
# Copyright 1998 Gerald Combs
#
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import print_function

import argparse
import difflib
import os
import subprocess
import sys
import tempfile


parser = argparse.ArgumentParser()
parser.add_argument('commit', nargs='?', default='HEAD',
                    help='Commit ID to be checked (default %(default)s)')


def print_git_user_instructions():
    print('To configure your name and email for git, run:')
    print('')
    print('  git config --global user.name "Your Name"')
    print('  git config --global user.email "you@example.com"')
    print('')
    print('After that update the author of your latest commit with:')
    print('')
    print('  git commit --amend --reset-author --no-edit')
    print('')


def verify_name(name):
    name = name.lower().strip()
    forbidden_names = ('unknown', 'root', 'user', 'your name')
    if name in forbidden_names:
        return False
    # Warn about names without spaces. Sometimes it is a mistake where the
    # developer accidentally committed using the system username.
    if ' ' not in name:
        print("WARNING: name '%s' does not contain a space." % (name,))
        print_git_user_instructions()
    return True


def verify_email(email):
    email = email.lower().strip()
    try:
        user, host = email.split('@')
    except ValueError:
        # Lacks a '@' (e.g. a plain domain or "foo[AT]example.com")
        return False
    tld = host.split('.')[-1]

    # localhost, localhost.localdomain, my.local etc.
    if 'local' in tld:
        return False

    # Possibly an IP address
    if tld.isdigit():
        return False

    # forbid code.wireshark.org. Submissions could be submitted by other
    # addresses if one would like to remain anonymous.
    if host.endswith('.wireshark.org'):
        return False

    # For documentation purposes only.
    if host == 'example.com':
        return False

    # 'peter-ubuntu32.(none)'
    if '(none)' in host:
        return False

    return True


def tools_dir():
    if __file__.endswith('.py'):
        # Assume direct invocation from tools directory
        return os.path.dirname(__file__)
    # Otherwise it is a git hook. To support git worktrees, do not manually look
    # for the .git directory, but query the actual top level instead.
    cmd = ['git', 'rev-parse', '--show-toplevel']
    srcdir = subprocess.check_output(cmd, universal_newlines=True).strip()
    return os.path.join(srcdir, 'tools')


def extract_subject(subject):
    '''Extracts the original subject (ignoring the Revert prefix).'''
    subject = subject.rstrip('\r\n')
    prefix = 'Revert "'
    suffix = '"'
    while subject.startswith(prefix) and subject.endswith(suffix):
        subject = subject[len(prefix):-len(suffix)]
    return subject


def verify_body(body):
    old_lines = body.splitlines(True)
    is_good = True
    if len(old_lines) >= 2 and old_lines[1].strip():
        print('ERROR: missing blank line after the first subject line.')
        is_good = False
    cleaned_subject = extract_subject(old_lines[0])
    if len(cleaned_subject) > 80:
        # Note that this is currently also checked by the commit-msg hook.
        print('Warning: keep lines in the commit message under 80 characters.')
        is_good = False
    if not is_good:
        print('''
Please rewrite your commit message to our standards, matching this format:

    component: a very brief summary of the change

    A commit message should start with a brief summary, followed by a single
    blank line and an optional longer description. If the change is specific to
    a single protocol, start the summary line with the abbreviated name of the
    protocol and a colon.

    Use paragraphs to improve readability. Limit each line to 80 characters.

''')
    if any(line.startswith('Bug:') or line.startswith('Ping-Bug:') for line in old_lines):
        sys.stderr.write('''
To close an issue, use "Closes #1234" or "Fixes #1234" instead of "Bug: 1234".
To reference an issue, use "related to #1234" instead of "Ping-Bug: 1234". See
https://docs.gitlab.com/ee/user/project/issues/managing_issues.html#closing-issues-automatically
for details.
''')
        return False

    try:
        cmd = ['git', 'stripspace']
        gs_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
        newbody, _ = gs_proc.communicate(body)
    except OSError as ex:
        print('Warning: unable to invoke git stripspace: %s' % (ex,))
        return is_good
    if newbody != body:
        new_lines = newbody.splitlines(True)
        diff = difflib.unified_diff(old_lines, new_lines,
                                    fromfile='OLD/.git/COMMIT_EDITMSG',
                                    tofile='NEW/.git/COMMIT_EDITMSG')
        # Clearly mark trailing whitespace (GNU patch supports such comments).
        diff = [
            '# NOTE: trailing space on the next line\n%s' % (line,)
            if len(line) > 2 and line[-2].isspace() else line
            for line in diff
        ]
        print('The commit message does not follow our standards.')
        print('Please rewrite it (there are likely whitespace issues):')
        print('')
        print(''.join(diff))
        return False
    return is_good


def main():
    args = parser.parse_args()
    commit = args.commit
    cmd = ['git', 'show', '--no-patch',
           '--format=%h%n%an%n%ae%n%B', commit, '--']
    output = subprocess.check_output(cmd, universal_newlines=True)
    # For some reason there is always an additional LF in the output, drop it.
    if output.endswith('\n\n'):
        output = output[:-1]
    abbrev, author_name, author_email, body = output.split('\n', 3)
    subject = body.split('\n', 1)[0]

    # If called directly (from the tools directory), print the commit that was
    # being validated. If called from a git hook (without .py extension), try to
    # remain silent unless there are issues.
    if __file__.endswith('.py'):
        print('Checking commit: %s %s' % (abbrev, subject))

    exit_code = 0
    if not verify_name(author_name):
        print('Disallowed author name: {}'.format(author_name))
        exit_code = 1

    if not verify_email(author_email):
        print('Disallowed author email address: {}'.format(author_email))
        exit_code = 1

    if exit_code:
        print_git_user_instructions()

    if not verify_body(body):
        exit_code = 1

    return exit_code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as ex:
        print('\n%s' % ex)
        sys.exit(ex.returncode)
    except KeyboardInterrupt:
        sys.exit(130)