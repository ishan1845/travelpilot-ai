import React from 'react';

export default function IndianFlagBackground() {
  return (
    <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" aria-hidden="true">
      {/* High-Resolution Photo of Alpine Lake & Mountain Covering All Background */}
      <picture>
        <source srcSet="/images/alpine_lake_mountain_bg.webp" type="image/webp" />
        <img
          src="/images/alpine_lake_mountain_bg.jpg"
          alt="Scenic Alpine Mountain and Glacial Lake Background"
          className="w-full h-full object-cover object-center fixed inset-0 scale-[1.002]"
          style={{ 
            imageRendering: 'high-quality',
            WebkitImageRendering: '-webkit-optimize-contrast',
            filter: 'contrast(1.05) saturate(1.05) brightness(1.02)'
          }}
          loading="eager"
          fetchpriority="high"
        />
      </picture>

      {/* Very light subtle gradient to keep maximum clarity of mountains and turquoise water */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-transparent to-black/15 pointer-events-none" />
    </div>
  );
}

