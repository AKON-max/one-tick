import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Public assets must never enter auth redirects. A redirected media request
  // returns HTML, which makes the browser report the MP4/MP3 as unplayable.
  if (/\.[a-z0-9]+$/i.test(pathname)) {
    return NextResponse.next();
  }

  // Public routes（/api 与 /ws 已从 matcher 排除，不走此守卫）
  const publicPaths = ["/", "/login", "/register"];
  const isPublicPath = publicPaths.some((p) => pathname === p);

  if (isPublicPath) {
    return NextResponse.next();
  }

  // Check for session cookie（FastAPI JWT，与 /api/auth/me 一致）
  const sessionCookie = request.cookies.get("session_token")?.value;

  if (!sessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // /api 与 /ws 由网关（生产 nginx / 开发 rewrites）转发到 FastAPI，鉴权由后端负责，不进入页面守卫
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|.*\\..*|uploads|api|ws).*)",
  ],
};
