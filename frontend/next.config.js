/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  images: {
    domains: [
      process.env.NEXT_PUBLIC_SUPABASE_URL?.replace('https://', '').split('/')[0],
      'vykso.com',
      'localhost',
    ].filter(Boolean),
  },
  // Ensure UTF-8 encoding and security headers
  async headers() {
    return [
      {
        // Apply UTF-8 only to HTML pages, not to static assets (CSS, JS, images)
        source: '/:path*',
        headers: [
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block',
          },
        ],
      },
      {
        // Apply Content-Type only to HTML files
        source: '/:path((?!.*\\.(js|css|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot)).*)',
        headers: [
          {
            key: 'Content-Type',
            value: 'text/html; charset=utf-8',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
