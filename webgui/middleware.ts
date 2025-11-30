import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// 公开路由（无需认证）
const publicPaths = ['/login', '/api/health'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 允许访问公开路由
  if (publicPaths.some(path => pathname.startsWith(path))) {
    return NextResponse.next();
  }

  // 允许访问静态资源
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon') ||
    pathname.includes('.')
  ) {
    return NextResponse.next();
  }

  // 检查 cookie 或 header 中的 token（服务端）
  // 注意：实际 token 存储在 localStorage，这里只做基础保护
  // 真正的验证在客户端组件中进行
  
  // 对于需要认证的路由，让客户端处理
  // 客户端会检查 localStorage 中的 token
  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
