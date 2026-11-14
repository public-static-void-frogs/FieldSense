import type { ButtonProps } from 'antd';
import { Button } from 'antd';
import type { MouseEvent } from 'react';
import type { LinkProps } from 'react-router-dom';
import { useHref, useLinkClickHandler } from 'react-router-dom';

// Ant Design styling with React Router's native link and modifier-key behavior.
type RouterButtonProps = Omit<ButtonProps, 'href'> &
  Pick<LinkProps, 'to' | 'replace' | 'state' | 'preventScrollReset' | 'relative'>;

export function RouterButton({
  to,
  replace,
  state,
  preventScrollReset,
  relative,
  onClick,
  ...props
}: RouterButtonProps) {
  const href = useHref(to, { relative });
  const handleClick = useLinkClickHandler(to, {
    replace,
    state,
    preventScrollReset,
    relative,
    target: props.target,
  });

  return (
    <Button
      {...props}
      href={href}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) {
          handleClick(event as MouseEvent<HTMLAnchorElement>);
        }
      }}
    />
  );
}
