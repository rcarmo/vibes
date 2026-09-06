"""Read-only stdio MCP server for Vibes messages. No HTTP listener or migrations."""
import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import aiosqlite
from vibes.message_tools import MessageTools

TOOL = {
    'name': 'messages',
    'description': 'Retrieve message references by row ID or search message text within the configured scope. Read-only, bounded and paginated.',
    'inputSchema': {
        'type': 'object', 'additionalProperties': False, 'required': ['action'],
        'properties': {
            'action': {'type': 'string', 'enum': ['get', 'search']},
            'row_ids': {'type': 'array', 'minItems': 1, 'maxItems': 50, 'items': {'type': 'integer', 'minimum': 1}},
            'query': {'type': 'string', 'maxLength': 500},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50, 'default': 10},
            'before_row': {'type': 'integer', 'minimum': 1},
        },
    },
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False},
}


class MessagesMCP:
    def __init__(self, tools):
        self.tools = tools
        self.initialized = False

    async def handle(self, request):
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}
        method = request['method']
        if 'id' not in request:
            return None
        response = {'jsonrpc': '2.0', 'id': request['id']}
        params = request.get('params', {})
        try:
            if not isinstance(params, dict):
                raise ValueError('Invalid params')
            if method == 'initialize':
                self.initialized = True
                requested = params.get('protocolVersion')
                version = requested if requested in {'2024-11-05', '2025-03-26', '2025-06-18'} else '2025-06-18'
                result = {'protocolVersion': version, 'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'vibes-messages', 'version': '1.0.0'}}
            elif method == 'ping':
                result = {}
            elif not self.initialized:
                raise ValueError('Initialize first')
            elif method == 'tools/list':
                result = {'tools': [TOOL]}
            elif method == 'tools/call':
                if params.get('name') != 'messages':
                    raise ValueError('Unknown tool')
                arguments = params.get('arguments', {})
                if not isinstance(arguments, dict) or set(arguments) - set(TOOL['inputSchema']['properties']):
                    raise ValueError('Invalid tool arguments')
                try:
                    value = await self.tools.query(**arguments)
                    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]}
                except (ValueError, TypeError, sqlite3.Error):
                    result = {'isError': True, 'content': [{'type': 'text', 'text': 'Invalid message query or unavailable message store.'}]}
            else:
                response['error'] = {'code': -32601, 'message': 'Method not found'}
                return response
            response['result'] = result
        except ValueError as exc:
            response['error'] = {'code': -32602, 'message': str(exc)}
        return response


async def serve(database, thread_id=None, workspace_access=False):
    uri = Path(database).resolve().as_uri() + '?mode=ro'
    async with aiosqlite.connect(uri, uri=True) as connection:
        connection.row_factory = aiosqlite.Row
        await connection.execute('PRAGMA query_only=ON')
        server = MessagesMCP(MessageTools(connection, thread_id=thread_id, workspace_access=workspace_access))
        while True:
            line = await asyncio.to_thread(sys.stdin.buffer.readline, 65537)
            if not line:
                break
            if len(line) > 65536:
                # Close rather than interpreting fragments of an oversized frame.
                break
            try:
                response = await server.handle(json.loads(line))
            except (ValueError, UnicodeError):
                response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--thread-id', type=int)
    scope.add_argument('--workspace-access', action='store_true')
    args = parser.parse_args()
    if args.thread_id is not None and args.thread_id < 1:
        parser.error('--thread-id must be positive')
    asyncio.run(serve(args.database, args.thread_id, args.workspace_access))


if __name__ == '__main__':
    main()
