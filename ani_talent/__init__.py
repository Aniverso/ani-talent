#!/usr/bin/env python3
"""Ani talent database client for a person or an Agent with an account.

Python 3.9 or later, no other package. An admin gives you an account and a role.
Your role decides which commands work. Installed as the command `ani-talent`; the
file also runs as `python3 ani_talent.py`.

  ani_talent.py guide                     # How to use this tool, for a person or an Agent.
  ani_talent.py login EMAIL               # Sends a code to your mailbox.
  ani_talent.py verify EMAIL CODE         # Starts the session (kept for this computer).
  ani_talent.py status                    # The account of the session and its end time.
  ani_talent.py logout

  ani_talent.py candidate ID              # One candidate. ID: an Ani ID (Ani000123) or a UUID.
  ani_talent.py summary ID                # Current title, company, city and function codes.
  ani_talent.py education ID              # Education rows and the city that the resume states.
  ani_talent.py contacts ID               # Contact values. Needs contact.read.
  ani_talent.py history ID                # The revisions of one candidate.
  ani_talent.py file ID [--out DIR]       # Save the original resume file (PDF or Word). Needs file.read.
  ani_talent.py search [--text TEXT] [WORD...] [--city CODE] [--function CODE]
                       [--min-degree DEGREE] [--min-months N] [--include-unknown] [--limit N]
                                          # Candidates by meaning (--text), words and filters.
                                          # A list of summaries.
  ani_talent.py jobs [--query TEXT] [--limit N] [--cursor JSON]
  ani_talent.py jobs --text TEXT [--limit N] [--city CODE] [--function CODE]   # Jobs by meaning.
  ani_talent.py job ID
  ani_talent.py match-job JOB_ID [--limit N] [--city CODE] [--function CODE] [--min-months N]
  ani_talent.py match-candidate CANDIDATE_ID [--limit N] [--city CODE] [--function CODE]
  ani_talent.py tags [--kind city|function]    # The codes for --city and --function.

  ani_talent.py mcp                       # A Model Context Protocol server on stdin and stdout.

For an Agent that uses MCP (Codex, Claude Code, Cursor and others), add this server
with the command `ani-talent mcp`. Its tools are the commands above, with the same
account, role and limits.

Output is JSON on stdout. A failure is JSON on stderr with exit code 1:
`http_status` 403 = your role does not allow the command; 429 = the daily limit of
your role is reached (it starts again at 00:00 Asia/Shanghai); 401 = sign in again.
Each read is recorded with your account. The files are in `~/.config/ani-talent/`
(mode 600): `session.json`. Do not copy `session.json` to another person.
"""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote, urlsplit

BASE = 'https://vnpidbfkvfytudqvsjfm.supabase.co'
VERSION = '0.2.0'
# The publishable key identifies the project. It is not a secret: with no account it reads nothing.
DEFAULT_KEY = 'sb_publishable_WY1XKEoEkXumGKcTTdrRag_SQtvl_AK'
KEY_SHA256 = 'f30517481a7374eda124db8e06192032eb0f2dd2da15223c746911f7d4cedf6d'
HOME = Path(os.environ.get('ANI_TALENT_HOME') or Path.home() / '.config' / 'ani-talent')
REFRESH_BEFORE = 120  # Seconds before the end of a session at which a call gets a new one.
ANI_ID = re.compile(r'Ani[0-9]{6,}\Z')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
FILE_LIMIT = 20971520


class Failure(Exception):
    def __init__(self, error, **details):
        super().__init__(error)
        self.report = {'error': error, **details}


def read(name):
    try:
        return json.loads((HOME / name).read_text())
    except (OSError, ValueError):
        return None


def write(name, value):
    HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = HOME / name
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(value))


def key():
    value = (read('client.json') or {}).get('publishable_key') or DEFAULT_KEY
    if not isinstance(value, str) or not value:
        raise Failure('not_set_up', hint='Run: ani-talent setup PUBLISHABLE_KEY')
    return value


_connection = None  # One connection for the process: a new one costs about a second.


def exchange(method, path, payload, headers, limit=8_000_001):
    global _connection
    target = urlsplit(BASE)
    kind = http.client.HTTPSConnection if target.scheme == 'https' else http.client.HTTPConnection
    while True:
        reused = _connection is not None
        if not reused:
            _connection = kind(target.hostname, target.port, timeout=30)
        try:
            _connection.request(method, path, payload, headers)
            response = _connection.getresponse()
            raw = response.read(limit)
            return response, raw
        except (OSError, http.client.HTTPException):
            _connection.close()
            _connection = None
            # The server closes an idle connection. Only then is a second try safe.
            if not reused:
                raise Failure('network_failed') from None


def request(path, body, token=None, schema=None):
    headers = {'apikey': key(), 'Content-Type': 'application/json', 'Cache-Control': 'no-store'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if schema:
        headers['Content-Profile'] = headers['Accept-Profile'] = schema
    response, raw = exchange('POST', path, json.dumps(body).encode(), headers)
    try:
        value = json.loads(raw) if raw else None
    except ValueError:
        value = None
    return response.status, value


def keep(session):
    """Store the session of an Auth reply. The token must be for this project."""
    try:
        token, user = session['access_token'], session['user']
        part = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        if claims['iss'] != BASE + '/auth/v1' or claims['sub'] != user['id']:
            raise ValueError()
        value = {'access_token': token, 'refresh_token': session['refresh_token'],
                 'expires_at': int(claims['exp']), 'email': user['email'], 'user_id': user['id']}
    except (KeyError, TypeError, ValueError, IndexError):
        raise Failure('sign_in_failed') from None
    write('session.json', value)
    return value


def token():
    key()  # A client that is not set up says so first.
    session = read('session.json')
    if not session:
        raise Failure('not_signed_in', hint='Run: ani-talent login EMAIL')
    if session['expires_at'] - time.time() > REFRESH_BEFORE:
        return session['access_token']
    status, value = request('/auth/v1/token?grant_type=refresh_token',
                            {'refresh_token': session['refresh_token']})
    if status != 200:
        (HOME / 'session.json').unlink(missing_ok=True)
        raise Failure('session_ended', hint='Run: ani-talent login EMAIL')
    return keep(value)['access_token']


def call(operation, **parameters):
    body = {name: value for name, value in parameters.items() if value is not None}
    status, value = request('/rest/v1/rpc/' + operation, body, token(), 'api')
    if status != 200:
        code = value.get('code') if isinstance(value, dict) else None
        raise Failure('request_refused', operation=operation, http_status=status, code=code)
    if value is None:  # The database gives null for an ID that is absent or that the account cannot read.
        raise Failure('not_found', operation=operation,
                      hint='No record has this ID, or your account cannot read it.')
    return value


def search(text, **body):
    """Search by meaning: the server makes the vector of the text."""
    status, value = request('/functions/v1/talent-search',
                            {'text': text, **{name: item for name, item in body.items() if item is not None}},
                            token())
    if status != 200:
        code = value.get('code') if isinstance(value, dict) else None
        raise Failure('request_refused', operation='talent-search', http_status=status, code=code)
    return value


def resolve(value):
    """The UUID of a candidate ID: a UUID stays; an Ani ID is looked up."""
    value = str(value).strip()
    if UUID.fullmatch(value.lower()):
        return value.lower()
    if not ANI_ID.fullmatch(value):
        raise Failure('invalid_candidate_id', hint='Use an Ani ID such as Ani000123, or a UUID.')
    found = [item['candidate_id'] for item in call('ani_ids', p_ids=[value]) if item.get('ani_id') == value]
    if not found:
        raise Failure('candidate_not_found', id=value)
    return found[0]


def with_ani_ids(value, *ids):
    """Add `ani_id` next to each `candidate_id` of a result. The result stays as it is on a failure."""
    found, stack = set(ids), [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if isinstance(item.get('candidate_id'), str) and UUID.fullmatch(item['candidate_id']):
                found.add(item['candidate_id'])
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    if not found:
        return value
    try:
        names = {}
        found = sorted(found)
        for start in range(0, len(found), 200):
            names.update({item['candidate_id']: item['ani_id'] for item in call('ani_ids', p_ids=found[start:start + 200])})
    except Failure:
        return value
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get('candidate_id') in names:
                item['ani_id'] = names[item['candidate_id']]
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    if isinstance(value, dict) and len(ids) == 1 and ids[0] in names:
        value.setdefault('ani_id', names[ids[0]])
    return value


def save_file(candidate, directory):
    """Save the newest original file of a candidate. The download is checked against its hash."""
    try:
        meta = call('candidate_file_get', p_candidate_id=candidate)
    except Failure as failure:
        if failure.report['error'] != 'not_found':
            raise
        raise Failure('no_file', hint='This candidate has no original file, or you cannot read the candidate.') from None
    if (not isinstance(meta, dict) or not re.fullmatch(r'original/[0-9a-f/-]+\.(pdf|docx|doc)', meta.get('object_key', ''))
            or not re.fullmatch(r'Ani[0-9]{6,}\.(pdf|docx|doc)', meta.get('file_name', ''))):
        raise Failure('response_rejected')
    response, raw = exchange('GET', '/storage/v1/object/authenticated/ani-talent-originals/'
                             + quote(meta['object_key'], safe='/'), None,
                             {'apikey': key(), 'Authorization': 'Bearer ' + token(), 'Cache-Control': 'no-store'},
                             FILE_LIMIT + 1)
    if response.status != 200:
        raise Failure('download_refused', http_status=response.status)
    if len(raw) != meta['bytes'] or hashlib.sha256(raw).hexdigest() != meta['sha256']:
        raise Failure('download_damaged')
    folder = Path(directory or '.').expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / meta['file_name']
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_bytes(raw)
    return {'candidate_id': candidate, 'ani_id': meta['ani_id'], 'path': str(path.resolve()),
            'bytes': meta['bytes'], 'sha256': meta['sha256']}


def filters(arguments, names):
    chosen = {name: getattr(arguments, name) for name in names if getattr(arguments, name) is not None}
    return chosen


ID = {'type': 'string', 'description': 'An Ani ID (Ani000123) or a UUID'}
LIMIT = {'type': 'integer', 'minimum': 1, 'maximum': 50}
CODE = {'type': 'string', 'description': 'A dictionary code from the tool tags, for example city.shanghai'}
# MCP tool: (description, properties, required, positional arguments, options).
TOOLS = {
    'login': ('Send a sign-in code to the mailbox of the account.', {'email': {'type': 'string'}}, ['email'],
              ['email'], []),
    'verify': ('Start the session with the code from the mailbox.',
               {'email': {'type': 'string'}, 'code': {'type': 'string'}}, ['email', 'code'], ['email', 'code'], []),
    'status': ('The account of the session and its end time.', {}, [], [], []),
    'candidate': ('One candidate: career, skills and current values.', {'id': ID}, ['id'], ['id'], []),
    'summary': ('Current title, company, city codes and function codes of one candidate.', {'id': ID}, ['id'],
                ['id'], []),
    'education': ('Education rows, highest degree and the city that the resume states for one candidate.',
                  {'id': ID}, ['id'], ['id'], []),
    'contacts': ('Contact values of one candidate. Counts for the daily contact limit.', {'id': ID}, ['id'],
                 ['id'], []),
    'history': ('The revisions of one candidate.', {'id': ID}, ['id'], ['id'], []),
    'file': ('Save the original resume file (PDF or Word) of one candidate to a folder on this computer, as '
             '<Ani ID>.pdf. Needs file.read (role pm). Counts for the daily file limit.',
             {'id': ID, 'out': {'type': 'string', 'description': 'Folder. Default: the current folder.'}},
             ['id'], ['id'], ['out']),
    'search': ('Candidates by meaning, words and filters, best first: a list of summaries with no name. text: one '
               'sentence that says which person you look for (search by meaning). terms: 8 words at most, a '
               'candidate with one of them is a hit (skill, company, title, school). Use text and terms together '
               'for the best order. A filter removes a candidate with no value for it, unless include_unknown is '
               'true. Search more than one time with different texts for a full list.',
               {'text': {'type': 'string', 'maxLength': 400}, 'terms': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 8}, 'city': CODE,
                'function': CODE, 'min_degree': {'type': 'string', 'enum': ['high_school', 'associate', 'bachelor',
                                                                            'master', 'doctor']},
                'min_months': {'type': 'integer', 'minimum': 0}, 'include_unknown': {'type': 'boolean'},
                'limit': LIMIT}, [], ['terms'],
               ['text', 'city', 'function', 'min-degree', 'min-months', 'include-unknown', 'limit']),
    'jobs': ('Jobs. With text: by meaning, best first. With query or nothing: newest first.',
             {'text': {'type': 'string', 'maxLength': 400}, 'query': {'type': 'string'}, 'city': CODE,
              'function': CODE, 'limit': LIMIT}, [], [], ['text', 'query', 'city', 'function', 'limit']),
    'job': ('One job.', {'id': ID}, ['id'], ['id'], []),
    'match-job': ('The candidates for one job, by meaning, best first. A list to examine, not a decision.',
                  {'id': ID, 'limit': LIMIT, 'city': CODE, 'function': CODE,
                   'min_months': {'type': 'integer', 'minimum': 0}}, ['id'], ['id'],
                  ['limit', 'city', 'function', 'min-months']),
    'match-candidate': ('The jobs for one candidate, by meaning, best first.',
                        {'id': ID, 'limit': LIMIT, 'city': CODE, 'function': CODE}, ['id'], ['id'],
                        ['limit', 'city', 'function']),
    'guide': ('How to use these tools: the search method, the roles, the limits and the rules. '
              'Read it one time before the first search.', {}, [], [], []),
    'tags': ('The city and function codes.', {'kind': {'type': 'string', 'enum': ['city', 'function']}}, [], [],
             ['kind']),
}


def tool_call(name, given):
    """Run one tool as the same command. Returns the text and the error mark."""
    if name not in TOOLS or not isinstance(given, dict):
        return json.dumps({'error': 'unknown_tool'}), True
    _, properties, required, positional, options = TOOLS[name]
    if any(key not in given for key in required) or any(key not in properties for key in given):
        return json.dumps({'error': 'invalid_arguments'}), True
    argv = [name]
    for key in positional:
        value = given.get(key, [])
        argv += [str(item) for item in value] if isinstance(value, list) else [str(value)]
    for option in options:
        value = given.get(option.replace('-', '_'))
        if value is True:
            argv.append('--' + option)
        elif value is not None and value is not False:
            argv += ['--' + option, str(value)]
    try:
        return json.dumps(main(argv), ensure_ascii=False), False
    except Failure as failure:
        return json.dumps(failure.report, ensure_ascii=False), True
    except SystemExit:  # The argument parser refused a value.
        return json.dumps({'error': 'invalid_arguments'}), True


def serve():
    """Model Context Protocol over stdin and stdout: one JSON-RPC message on each line."""
    for line in sys.stdin:
        try:
            message = json.loads(line)
            method, number = message.get('method'), message.get('id')
        except (ValueError, AttributeError):
            continue
        if number is None:
            continue  # A notification has no reply.
        parameters = message.get('params') or {}
        error = None
        if method == 'initialize':
            result = {'protocolVersion': parameters.get('protocolVersion') or '2025-06-18',
                      'capabilities': {'tools': {}}, 'serverInfo': {'name': 'ani-talent', 'version': VERSION},
                      'instructions': 'Read the Ani talent database with the account of this computer. '
                                      'Each read is recorded. Do not copy many records out. '
                                      'Call the tool `guide` one time before the first search.'}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': [{'name': name, 'description': description,
                                 'inputSchema': {'type': 'object', 'properties': properties, 'required': required,
                                                 'additionalProperties': False}}
                                for name, (description, properties, required, _, _) in TOOLS.items()]}
        elif method == 'tools/call':
            text, failed = tool_call(parameters.get('name'), parameters.get('arguments') or {})
            result = {'content': [{'type': 'text', 'text': text}], 'isError': failed}
        else:
            result, error = None, {'code': -32601, 'message': 'Method not found'}
        reply = {'jsonrpc': '2.0', 'id': number, **({'error': error} if error else {'result': result})}
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + '\n')
        sys.stdout.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('setup').add_argument('publishable_key')
    commands.add_parser('login').add_argument('email')
    command = commands.add_parser('verify')
    command.add_argument('email')
    command.add_argument('code')
    commands.add_parser('status')
    commands.add_parser('logout')
    for name in ('candidate', 'summary', 'education', 'contacts', 'history', 'job'):
        commands.add_parser(name).add_argument('id')
    command = commands.add_parser('file')
    command.add_argument('id')
    command.add_argument('--out')
    command = commands.add_parser('search')
    command.add_argument('terms', nargs='*')
    command.add_argument('--text')
    command.add_argument('--city')
    command.add_argument('--function')
    command.add_argument('--min-degree', dest='min_degree',
                         choices=('high_school', 'associate', 'bachelor', 'master', 'doctor'))
    command.add_argument('--min-months', dest='min_months', type=int)
    command.add_argument('--include-unknown', dest='include_unknown', action='store_true', default=None)
    command.add_argument('--limit', type=int, default=20)
    command = commands.add_parser('jobs')
    command.add_argument('--query')
    command.add_argument('--text')
    command.add_argument('--city')
    command.add_argument('--function')
    command.add_argument('--limit', type=int, default=20)
    command.add_argument('--cursor', type=json.loads)
    for name in ('match-job', 'match-candidate'):
        command = commands.add_parser(name)
        command.add_argument('id')
        command.add_argument('--limit', type=int, default=20)
        command.add_argument('--city')
        command.add_argument('--function')
        if name == 'match-job':
            command.add_argument('--min-months', dest='min_months', type=int)
    commands.add_parser('tags').add_argument('--kind', choices=('city', 'function'))
    commands.add_parser('mcp')
    commands.add_parser('guide')
    commands.add_parser('version')
    arguments = parser.parse_args(argv)

    if arguments.command == 'version':
        return {'version': VERSION}
    if arguments.command == 'guide':
        try:
            return {'guide': Path(__file__).with_name('SKILL.md').read_text()}
        except OSError:
            raise Failure('guide_not_found', hint='Read SKILL.md next to this tool.')
    if arguments.command == 'setup':
        if hashlib.sha256(arguments.publishable_key.encode()).hexdigest() != KEY_SHA256:
            raise Failure('wrong_key', hint='This is not the publishable key of the Ani talent project.')
        write('client.json', {'publishable_key': arguments.publishable_key})
        return {'status': 'set_up'}
    if arguments.command == 'login':
        status, _ = request('/auth/v1/otp', {'email': arguments.email.strip().lower(), 'create_user': False})
        if status != 200:
            raise Failure('code_not_sent', http_status=status,
                          hint='The email has no account, or too many codes were sent. Ask your admin.')
        return {'status': 'code_sent', 'next': 'ani-talent verify EMAIL CODE'}
    if arguments.command == 'verify':
        status, value = request('/auth/v1/verify', {'email': arguments.email.strip().lower(),
                                                    'token': arguments.code.strip(), 'type': 'email'})
        if status != 200:
            raise Failure('code_refused', http_status=status)
        session = keep(value)
        return {'status': 'signed_in', 'email': session['email']}
    if arguments.command == 'status':
        session = read('session.json')
        if not session:
            return {'signed_in': False}
        return {'signed_in': True, 'email': session['email'],
                'session_ends_in_seconds': max(0, int(session['expires_at'] - time.time()))}
    if arguments.command == 'logout':
        session = read('session.json')
        if session:
            request('/auth/v1/logout?scope=local', {}, session['access_token'])
            (HOME / 'session.json').unlink(missing_ok=True)
        return {'status': 'signed_out'}

    one = {'candidate': 'candidate_get', 'summary': 'candidate_summary', 'education': 'candidate_derived_get',
           'contacts': 'contacts_get', 'history': 'candidate_history'}
    if arguments.command in one:
        candidate = resolve(arguments.id)
        return with_ani_ids(call(one[arguments.command], p_candidate_id=candidate), candidate)
    if arguments.command == 'file':
        return save_file(resolve(arguments.id), arguments.out)
    if arguments.command == 'search' and arguments.text:
        return with_ani_ids(search(arguments.text, words=' '.join(arguments.terms) or None, limit=arguments.limit,
                                   filters=filters(arguments, ('city', 'function', 'min_degree', 'min_months',
                                                               'include_unknown'))))
    if arguments.command == 'jobs' and arguments.text:
        return search(arguments.text, target='jobs', limit=arguments.limit,
                      filters=filters(arguments, ('city', 'function')))
    if arguments.command == 'search':
        return with_ani_ids(call('candidate_find', p_text=' '.join(arguments.terms) or None, p_limit=arguments.limit,
                                 p_filters=filters(arguments, ('city', 'function', 'min_degree', 'min_months',
                                                               'include_unknown'))))
    if arguments.command == 'jobs':
        return call('job_list', p_query=arguments.query, p_limit=arguments.limit, p_cursor=arguments.cursor)
    if arguments.command == 'job':
        return call('job_get', p_job_id=arguments.id)
    if arguments.command == 'match-job':
        return with_ani_ids(call('job_match_candidates', p_job_id=arguments.id, p_limit=arguments.limit,
                                 p_filters=filters(arguments, ('city', 'function', 'min_months'))))
    if arguments.command == 'match-candidate':
        candidate = resolve(arguments.id)
        return with_ani_ids(call('candidate_match_jobs', p_candidate_id=candidate, p_limit=arguments.limit,
                                 p_filters=filters(arguments, ('city', 'function'))), candidate)
    return call('dictionary_list', p_kind=arguments.kind)


def cli():
    """The entry point of the installed command."""
    if sys.argv[1:] == ['mcp']:
        serve()
        sys.exit(0)
    try:
        value = main()
    except Failure as failure:
        print(json.dumps(failure.report, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    # The guide is text for a reader; each other command prints JSON.
    if isinstance(value, dict) and set(value) == {'guide'}:
        print(value['guide'])
    else:  # A result can be a list (history).
        print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    cli()
