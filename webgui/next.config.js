/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  
  // API proxy to OLAV backend (development)
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/:path*`,
      },
    ];
  },

  // Internationalization (disabled for App Router static export)
  // i18n: {
  //   locales: ['zh', 'en'],
  //   defaultLocale: 'zh',
  // },
};

module.exports = nextConfig;
