# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.12-slim

# Node.js provides `npx`, which ADK's McpToolset uses to launch the Google Maps
# MCP server (`npx -y @modelcontextprotocol/server-google-maps`) over stdio.
# Without it, the find-a-provider / booking flows fail at runtime in-container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.8.13

WORKDIR /code

# Copy dependency manifests first so Docker can cache the (slow) dependency layer.
COPY ./pyproject.toml ./README.md ./uv.lock* ./

# Copy the ADK application package (the agent code lives in care_navigator/, not app/).
COPY ./care_navigator ./care_navigator

RUN uv sync --frozen

ARG COMMIT_SHA=""
ENV COMMIT_SHA=${COMMIT_SHA}

ARG AGENT_VERSION=0.0.0
ENV AGENT_VERSION=${AGENT_VERSION}

EXPOSE 8080

# Serve the FastAPI app defined in care_navigator/fast_api_app.py.
CMD ["uv", "run", "uvicorn", "care_navigator.fast_api_app:app", "--host", "0.0.0.0", "--port", "8080"]
