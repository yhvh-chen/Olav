# OLAV WebGUI

Next.js-based web interface for OLAV Enterprise Network Operations Platform.

## Features

- 🔄 **Real-time Streaming**: SSE-based response streaming with thinking process visualization
- 🧠 **Thinking Process Display**: Shows LLM reasoning steps, hypothesis, and verification
- 🔧 **Tool Call Indicators**: Real-time display of tool invocations
- 🛡️ **HITL Approval UI**: Interactive approval dialogs for write operations
- 🌙 **Dark Mode**: Default dark theme optimized for NOC environments
- 🌐 **i18n Ready**: Chinese/English internationalization support

## Quick Start

### Development

```bash
cd webgui

# Install dependencies
npm install

# Create environment file
cp .env.example .env.local

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Docker

```bash
# Build and run with docker-compose (from project root)
docker-compose --profile webgui up -d olav-webgui

# Or standalone
cd webgui
docker build -t olav-webgui:latest .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://localhost:8000 olav-webgui:latest
```

## Project Structure

```
webgui/
├── app/                    # Next.js App Router
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Home (redirects to /chat)
│   ├── globals.css        # Global styles
│   └── chat/
│       └── page.tsx       # Main chat interface
├── lib/
│   ├── api/               # API client & types
│   │   ├── client.ts
│   │   └── types.ts
│   └── stores/            # Zustand state management
│       ├── auth-store.ts
│       └── chat-store.ts
├── components/            # React components (TODO)
├── Dockerfile
├── package.json
├── tailwind.config.js
└── tsconfig.json
```

## API Integration

The WebGUI connects to OLAV backend via:

| Endpoint | Purpose |
|----------|---------|
| `POST /auth/login` | User authentication |
| `GET /config` | Public configuration |
| `GET /health` | Server health check |
| `POST /orchestrator/stream/events` | **New** Streaming with thinking events |

### Stream Event Types

```typescript
interface StreamEvent {
  type: 'token' | 'thinking' | 'tool_start' | 'tool_end' | 'interrupt' | 'error' | 'done';
  content?: string;      // For 'token'
  thinking?: {           // For 'thinking'
    step: 'hypothesis' | 'verification' | 'conclusion' | 'reasoning';
    content: string;
  };
  tool?: {               // For 'tool_start' / 'tool_end'
    name: string;
    display_name: string;
    duration_ms?: number;
  };
  execution_plan?: {...}; // For 'interrupt' (HITL)
  error?: {...};          // For 'error'
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | OLAV backend URL |
| `NEXT_PUBLIC_APP_NAME` | `OLAV` | Application name |
| `NEXT_PUBLIC_DEFAULT_LOCALE` | `zh` | Default language |

## Development Phases

- [x] Phase 1: Project scaffolding & API types
- [x] Phase 1: Backend streaming endpoint with thinking events
- [ ] Phase 2: Login page & authentication
- [ ] Phase 2: Chat interface with SSE streaming
- [ ] Phase 3: Thinking process visualization component
- [ ] Phase 3: HITL approval dialogs
- [ ] Phase 4: Topology visualization (React Flow)
- [ ] Phase 5: i18n & dark mode polish
- [ ] Phase 6: Production optimization

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS + shadcn/ui
- **State**: Zustand
- **Data Fetching**: TanStack Query
- **Streaming**: Native EventSource API
- **Visualization**: React Flow (planned)
