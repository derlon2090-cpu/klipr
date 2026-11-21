/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Browser calls stay same-origin (/api/*); Next performs the server-side
    // hop so local Docker and production never depend on a visitor's localhost.
    const backend = process.env.BACKEND_INTERNAL_URL || "http://api:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
