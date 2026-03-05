# audiobook-maker-
make an audiobook generator

## Vercel Website Launcher

This repository includes a lightweight Vercel launcher site that points users to run the Python Gradio app.

### Files added

- `vercel.json` - routes `/` to the static launcher page and exposes `/api/launch`.
- `website/index.html` - static launcher page with quick start commands.
- `api/launch.js` - optional JSON endpoint with launch instructions.

### Deploy to Vercel

1. Push this repository to GitHub.
2. In Vercel, create a new project and import this repository.
3. Deploy with default settings.

After deployment:

- Visiting `/` shows the launcher page.
- Visiting `/api/launch` returns machine-readable launch instructions.
