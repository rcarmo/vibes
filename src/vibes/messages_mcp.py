"""Read-only stdio MCP server for Vibes messages. No HTTP listener or migrations."""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import aiosqlite
from vibes.message_tools import MessageTools
from vibes.workspace_tools import WorkspaceTools
from vibes._vendor.umcp.aioumcp import AsyncMCPServer

TOOL = {
    'name': 'messages',
    'description': 'Retrieve message references by row ID or search message text within the configured scope. Use action=attachment with media_id to read bounded text previews of uploads referenced in scope. Binary uploads return metadata only. Read-only, bounded and paginated.',
    'inputSchema': {
        'type': 'object', 'additionalProperties': False, 'required': ['action'],
        'properties': {
            'action': {'type': 'string', 'enum': ['get', 'search', 'attachment']},
            'row_ids': {'type': 'array', 'minItems': 1, 'maxItems': 50, 'items': {'type': 'integer', 'minimum': 1}},
            'query': {'type': 'string', 'maxLength': 500},
            'media_id': {'type': 'integer', 'minimum': 1},
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

    def __init__(self, tools, workspace_root=None):
        super().__init__()
        self.tools = tools
        self.workspace = WorkspaceTools(workspace_root) if workspace_root else None
        if self.workspace:
            self.register_tool('workspace_list', self.workspace_list,
                description='List a bounded relative workspace directory without following symlinks. Root is dot; truncated listings are not exhaustive.',
                input_schema={'type': 'object', 'additionalProperties': False, 'properties': {
                    'path': {'type': 'string', 'default': '.'},
                    'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200, 'default': 100}}},
                annotations={'readOnlyHint': True, 'destructiveHint': False})
            self.register_tool('workspace_read', self.workspace_read,
                description='Read a bounded text preview of a relative workspace file. Byte offsets paginate. Symlinks and traversal are rejected.',
                input_schema={'type': 'object', 'additionalProperties': False, 'required': ['path'], 'properties': {
                    'path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0},
                    'limit': {'type': 'integer', 'minimum': 1, 'maximum': 24000}}},
                annotations={'readOnlyHint': True, 'destructiveHint': False})
        self.register_tool('messages', self.messages,
            description=TOOL['description'], input_schema=TOOL['inputSchema'],
            annotations=TOOL['annotations'])

    async def workspace_list(self, path: str = '.', limit: int = 100):
        if not self.workspace:
            raise ValueError('Workspace access not configured')
        return await asyncio.to_thread(self.workspace.list_directory, path, limit)

    async def workspace_read(self, path: str, offset: int = 0, limit: int = 24000):
        if not self.workspace:
            raise ValueError('Workspace access not configured')
        return await asyncio.to_thread(self.workspace.read, path, offset, limit)

    async def messages(self, action: str, row_ids=None, query: str = '', limit: int = 10, before_row=None, media_id=None):
        return await self.tools.query(action, row_ids=row_ids, query=query,
            limit=limit, before_row=before_row, media_id=media_id)

    async def handle(self, request):
        return await self.process_request_async(json.dumps(request))


async def serve(database, thread_id=None, workspace_access=False, workspace_root=None):
    uri = Path(database).resolve().as_uri() + '?mode=ro'
    async with aiosqlite.connect(uri, uri=True) as connection:
        connection.row_factory = aiosqlite.Row
        await connection.execute('PRAGMA query_only=ON')
        server = MessagesMCP(MessageTools(connection, thread_id=thread_id, workspace_access=workspace_access), workspace_root)
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
    parser.add_argument('--workspace-root', help='Explicitly enable bounded workspace reads')
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--thread-id', type=int)
    scope.add_argument('--workspace-access', action='store_true')
    args = parser.parse_args()
    if args.thread_id is not None and args.thread_id < 1:
        parser.error('--thread-id must be positive')
    asyncio.run(serve(args.database, args.thread_id, args.workspace_access, args.workspace_root))


if __name__ == '__main__':
    main()
