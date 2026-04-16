export async function startCloudProcess(payload) {
  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      let message = `Request failed (${res.status})`;
      try {
        const body = await res.json();
        if (body && body.message) {
          message = String(body.message);
        }
      } catch (_err) {
        // Ignore invalid JSON body.
      }
      return { ok: false, status: res.status, message };
    }
    const data = await res.json();
    return { ok: true, data };
  } catch (err) {
    return { ok: false, status: 0, message: err instanceof Error ? err.message : String(err) };
  }
}

export async function pollCloudProcess(jobId) {
  try {
    const res = await fetch(`/api/process?job_id=${encodeURIComponent(jobId)}`);
    if (!res.ok) {
      return { ok: false, status: res.status, message: `Polling failed (${res.status})` };
    }
    const data = await res.json();
    return { ok: true, data };
  } catch (err) {
    return { ok: false, status: 0, message: err instanceof Error ? err.message : String(err) };
  }
}

export async function fetchLaunchInfo() {
  try {
    const res = await fetch("/api/launch");
    if (!res.ok) {
      return { ok: false, status: res.status, message: `Launch API unavailable (${res.status})` };
    }
    const data = await res.json();
    return { ok: true, data };
  } catch (err) {
    return { ok: false, status: 0, message: err instanceof Error ? err.message : String(err) };
  }
}

export async function fetchHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) {
      return { ok: false, status: res.status, message: `Health API unavailable (${res.status})` };
    }
    const data = await res.json();
    return { ok: true, data };
  } catch (err) {
    return { ok: false, status: 0, message: err instanceof Error ? err.message : String(err) };
  }
}
