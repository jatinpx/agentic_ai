import { NextRequest, NextResponse } from "next/server";

const BACKEND_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

function popupHtml(status: "success" | "error", message: string) {
  const payload = JSON.stringify({ type: "linkedin-auth", status, message });
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>LinkedIn Auth</title>
  </head>
  <body style="font-family: sans-serif; padding: 20px;">
    <h3>${status === "success" ? "LinkedIn connected" : "LinkedIn connection failed"}</h3>
    <p>${message}</p>
    <script>
      (function () {
        try {
          if (window.opener) {
            window.opener.postMessage(${payload}, window.location.origin);
          }
        } catch (_) {}
        setTimeout(function () {
          window.close();
        }, 300);
      })();
    </script>
  </body>
</html>`;
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const code = searchParams.get("code");
  const state = searchParams.get("state");
  const error = searchParams.get("error");
  const errorDescription = searchParams.get("error_description");

  if (error) {
    return new NextResponse(
      popupHtml("error", errorDescription || `LinkedIn returned OAuth error: ${error}`),
      {
        status: 400,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      }
    );
  }

  if (!code) {
    return new NextResponse(popupHtml("error", "Missing authorization code."), {
      status: 400,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }

  const callbackParams = new URLSearchParams({ code });
  if (state) callbackParams.set("state", state);

  try {
    const backendRes = await fetch(`${BACKEND_BASE}/linkedin/auth/callback?${callbackParams.toString()}`, {
      method: "GET",
      cache: "no-store",
    });

    if (!backendRes.ok) {
      const payload = await backendRes.json().catch(() => ({}));
      const detail = payload?.detail || "OAuth callback failed on backend.";
      return new NextResponse(popupHtml("error", detail), {
        status: 400,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    return new NextResponse(
      popupHtml("success", "Authentication complete. You can close this window."),
      {
        status: 200,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      }
    );
  } catch {
    return new NextResponse(
      popupHtml("error", "Could not reach backend callback endpoint."),
      {
        status: 500,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      }
    );
  }
}
