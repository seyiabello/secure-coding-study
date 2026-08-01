export const maxDuration = 60;

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

async function handler(
  req: Request,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const search = new URL(req.url).search;
  const url = `${BACKEND}/${path.join("/")}${search}`;

  const init: RequestInit = {
    method: req.method,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  const upstream = await fetch(url, init);
  const body = await upstream.text();

  return new Response(body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export { handler as GET, handler as POST };
