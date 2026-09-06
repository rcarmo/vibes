"""Read-only stdio MCP server for Vibes messages. No HTTP listener or migrations."""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import aiosqlite
from vibes.message_tools import MessageTools
from vibes._vendor.umcp.aioumcp import AsyncMCPServer

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


class MessagesMCP(AsyncMCPServer):
    def _setup_logging(self):
        # Never create vendor-directory log files or put diagnostics on stdout.
        self.logger = logging.getLogger('vibes.messages_mcp')

    def __init__(self, tools):
        super().__init__()
        self.tools = tools
        self.register_tool('messages', self.messages,
            description=TOOL['description'], input_schema=TOOL['inputSchema'],
            annotations=TOOL['annotations'])

    async def messages(self, action: str, row_ids=None, query: str = '', limit: int = 10, before_row=None):
        return await self.tools.query(action, row_ids=row_ids, query=query,
            limit=limit, before_row=before_row)

    async def handle(self, request):
        return await self.process_request_async(json.dumps(request))


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
