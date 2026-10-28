# Classic session-owned media

POST `/api/sessions/{s}/media` accepts the existing multipart `file` upload,
up to 10 MiB. It uses the real upload/storage/thumbnail implementation, binds
ownership to the path session and returns `{media:{id,session_id,filename,name,
content_type,created_at}}`. Missing/archived sessions return 404. Query scope
injection, malformed multipart and oversized uploads return 400/413. Upload
progress and cancellation remain browser transfer responsibilities.

GET `/api/sessions/{s}/media/{id}` returns redacted media metadata. Append `/raw`
or `/thumbnail` for bytes; thumbnails fall back to original bytes when absent.
The compatible `/api/media/{id}` and `/api/media/{id}/raw|thumbnail` aliases
require exactly one explicit `session_id` query parameter. A numeric media ID
alone returns 400 and grants no canonical byte access. Missing/foreign/unowned
media return 404. Archived sessions remain readable.

Ownership requires dictionary-shaped persisted metadata with a matching session.
Validation and byte readback share the database write lock, avoiding a same-process
replacement race. Nullable/list legacy metadata fails closed; prompt validation
and conversation projection apply the same check. Metadata responses do not
expose arbitrary stored values or original URLs.

Raw and thumbnail serving reuse the existing MIME policy: raster images can be
inline; other formats, including HTML/SVG, get attachment disposition and sandbox
CSP. All canonical responses use `Cache-Control: no-store`; byte responses retain
`X-Content-Type-Options: nosniff`. Legacy global `/media/...` routes remain available
inside the trusted single-user compatibility surface.

Candidate `0259e9a` uploads to the correct scoped route, but its media info/raw URL
helpers supply no session selector. Those calls return 400. Shared-client URL
construction must carry explicit scope before media display/queue-return acceptance;
this backend does not weaken ownership to satisfy an unscoped URL.

## Verification

The full Python suite passed 1,041 tests with 13 existing skips in 41.56 seconds,
using the pinned optional SDK and unchanged shared assets. New/changed canonical
modules and tests pass Ruff; diff checks pass. HTTP tests cover upload shape,
active-content download protections, scoped/alias reads, thumbnail fallback,
foreign/unowned/repeated-scope rejection, legacy compatibility, archive/missing
sessions, malformed/oversized uploads and metadata redaction. Read-only review
found no further security/correctness issue in the scoped adapter.

No provider, complete browser client, live media rendering or release acceptance
was exercised. Temporary SDK, asset link and disposable test output are removed
after analysis. Candidate frontend scope adoption and pre-release CPU/allocation
profiling still require work.
