# Adapter: Jamie (meeting recorder, MCP server)

Jamie records meetings and exposes them through an MCP server. Its tools are **deferred** in Claude Code: load them before use, and resolve the server id by searching for a distinctive tool name rather than hard-coding it (the id is a UUID that differs per machine).

```
ToolSearch: list_meetings jamie meetings transcript
ToolSearch: select:mcp__<server-id>__list_meetings,mcp__<server-id>__get_meeting,mcp__<server-id>__get_meeting_transcript,mcp__<server-id>__list_tags,mcp__<server-id>__add_tag_to_meetings,mcp__<server-id>__create_tag
```

## Discovery

1. `list_tags` — confirm the vocabulary below exists; capture tag ids.
2. `list_meetings` with a `startDate` a little before the last known ingest, no tag filter — the candidate set.
3. `list_meetings` with `tag: "wf/ingested"` over the same window — already done.
4. `list_meetings` with `tag: "wf/skip"` — deliberately excluded.

New = candidates − ingested − skipped.

## Triage

`get_meeting` returns metadata, participants (with emails), Jamie's summary and extracted tasks, and roughly the first 10 KB of transcript. A duration of a few seconds with an empty transcript is a misfire → `wf/skip`.

## Full transcript

`get_meeting` truncates. Page with `get_meeting_transcript`, passing `nextCursor` until `isFinal: true`; pages are under 20 KB, so a two-hour meeting is four to five calls.

## Marker vocabulary

| Tag | Applies to |
|---|---|
| `wf/ingested` | successfully ingested — the idempotence marker |
| `wf/skip` | misfires, empty transcripts, deliberate exclusions |
| `org/<name>` | which organization or context the meeting belongs to |
| `type/1-1`, `type/sync`, `type/session`, `type/workshop`, `type/external`, `type/governance` | meeting shape |
| `dom/<domain>` | subject domains; several allowed |

`add_tag_to_meetings` takes one tag and a list of meeting ids; batch by tag. Apply `wf/ingested` only after the wiki write completed. `create_tag` exists; a growing vocabulary defeats the purpose, so propose additions to the owner instead of creating them.

Adjust the `org/` and `dom/` values to your own context in `CUSTOMIZATIONS.md`.
