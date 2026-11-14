import type { SVGProps } from 'react';

type WeatherConditionIconProps = SVGProps<SVGSVGElement> & {
  conditions: string;
  size?: number | string;
};

export function WeatherConditionIcon({
  conditions,
  size = 24,
  ...props
}: WeatherConditionIconProps) {
  const labelled = Boolean(props['aria-label'] || props['aria-labelledby']);

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role={labelled ? 'img' : undefined}
      aria-hidden={labelled ? undefined : true}
      {...props}
    >
      <WeatherSymbol conditions={conditions} />
    </svg>
  );
}

type WeatherSymbolProps = { conditions: string };

function WeatherSymbol({ conditions }: WeatherSymbolProps) {
  switch (conditions) {
    case 'Clear sky':
      return <WeatherSun />;
    case 'Partly cloudy':
      return (
        <>
          <g transform="translate(1 -5) scale(.82)">
            <WeatherSun />
          </g>
          <WeatherCloud />
        </>
      );
    case 'Overcast':
      return <WeatherCloud />;
    case 'Rain':
    case 'Drizzle':
      return (
        <>
          <g transform="translate(0 -7)">
            <WeatherCloud />
          </g>
          <g fill="#459be1">
            <path d="M20 44c0 0-5 6-5 9a5 5 0 0 0 10 0c0-3-5-9-5-9Z" />
            <path d="M34 47c0 0-4 5-4 8a4 4 0 0 0 8 0c0-3-4-8-4-8Z" />
            <path d="M47 43c0 0-4 5-4 8a4 4 0 0 0 8 0c0-3-4-8-4-8Z" />
          </g>
        </>
      );
    case 'Snow':
      return (
        <>
          <g transform="translate(0 -9)">
            <WeatherCloud />
          </g>
          <g stroke="#69b2e0" strokeWidth="2.8" strokeLinecap="round">
            <path d="M18 44v12m-5-9 10 6m-10 0 10-6M34 48v12m-5-9 10 6m-10 0 10-6M49 43v12m-5-9 10 6m-10 0 10-6" />
          </g>
        </>
      );
    case 'Thunderstorm':
      return (
        <>
          <g transform="translate(0 -7)">
            <WeatherCloud dark />
          </g>
          <path d="m32 36-9 15h9l-3 12 17-20H35l7-7H32Z" fill="#f8bd35" />
        </>
      );
    case 'Fog':
      return (
        <>
          <g transform="translate(0 -10)">
            <WeatherCloud />
          </g>
          <rect x="8" y="40" width="43" height="5" rx="2.5" fill="#9aafbd" />
          <rect x="15" y="49" width="42" height="5" rx="2.5" fill="#bacbd4" />
          <rect x="8" y="58" width="33" height="4" rx="2" fill="#d1dde3" />
        </>
      );
    default:
      return (
        <>
          <circle cx="32" cy="32" r="23" fill="#e7edf2" />
          <path
            d="M25 24a7 7 0 0 1 14 0c0 6-7 6-7 12"
            stroke="#7c91a2"
            strokeWidth="5"
            strokeLinecap="round"
          />
          <circle cx="32" cy="45" r="3" fill="#7c91a2" />
        </>
      );
  }
}

function WeatherSun() {
  return (
    <>
      <g fill="#f8c24e">
        <rect x="29" y="2" width="6" height="10" rx="3" />
        <rect x="29" y="52" width="6" height="10" rx="3" />
        <rect x="2" y="29" width="10" height="6" rx="3" />
        <rect x="52" y="29" width="10" height="6" rx="3" />
        <rect x="29" y="2" width="6" height="10" rx="3" transform="rotate(45 32 32)" />
        <rect x="29" y="52" width="6" height="10" rx="3" transform="rotate(45 32 32)" />
        <rect x="2" y="29" width="10" height="6" rx="3" transform="rotate(45 32 32)" />
        <rect x="52" y="29" width="10" height="6" rx="3" transform="rotate(45 32 32)" />
      </g>
      <circle cx="32" cy="32" r="17" fill="#f4ac32" />
      <circle cx="29" cy="29" r="14" fill="#ffd568" />
    </>
  );
}

type WeatherCloudProps = { dark?: boolean };

function WeatherCloud({ dark = false }: WeatherCloudProps) {
  return (
    <>
      <path
        d="M18 49C10 49 5 44 5 37c0-6 4-11 10-12 2-9 9-15 18-14 9 1 15 7 16 15 7 0 12 5 12 11 0 7-5 12-13 12H18Z"
        fill={dark ? '#617b93' : '#c4d4e1'}
      />
      <path
        d="M17 42c-5 0-9-3-9-8 1-4 4-7 9-7 2-8 8-13 15-13 8 0 14 6 14 14 6-1 11 2 12 7 0 4-4 7-9 7H17Z"
        fill={dark ? '#8199ad' : '#e5edf5'}
      />
    </>
  );
}
