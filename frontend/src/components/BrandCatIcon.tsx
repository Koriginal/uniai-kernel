import React from 'react';

interface BrandCatIconProps {
  size?: number;
  color?: string;
  strokeWidth?: number;
  className?: string;
  style?: React.CSSProperties;
}

const BrandCatIcon: React.FC<BrandCatIconProps> = ({
  size = 22,
  color = '#1677ff',
  strokeWidth = 1.9,
  className,
  style,
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      style={style}
      aria-hidden="true"
    >
      <path
        d="M6.2 10.6V6.9l3.1 2.7L12 7.7l2.7 1.9 3.1-2.7v3.7a5.8 5.8 0 0 1 1.8 4.3c0 3.3-2.7 6-6 6h-3.2c-3.3 0-6-2.7-6-6 0-1.7.7-3.2 1.8-4.3Z"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="9.4" cy="14.1" r="0.8" fill={color} />
      <circle cx="14.6" cy="14.1" r="0.8" fill={color} />
      <path d="M9.1 17h5.8" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
};

export default BrandCatIcon;
