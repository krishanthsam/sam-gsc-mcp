#!/usr/bin/env bash
# Add Sam GSC MCP to Claude Code (user scope = available in every project).
claude mcp add sam-gsc --scope user \
  -e GSC_OAUTH_CLIENT_SECRETS_FILE=/FULL/PATH/TO/client_secrets.json \
  -- uvx --from git+https://github.com/krishanthsam/sam-gsc-mcp sam-gsc-mcp

# Service account instead:
# claude mcp add sam-gsc --scope user \
#   -e GSC_CREDENTIALS_PATH=/FULL/PATH/TO/service_account.json -e GSC_SKIP_OAUTH=true \
#   -- uvx --from git+https://github.com/krishanthsam/sam-gsc-mcp sam-gsc-mcp
