import { useSuspenseQuery } from '@tanstack/react-query';
import { Avatar, Badge, Button, Layout, Menu, Tooltip } from 'antd';
import {
  Bell,
  CalendarDays,
  CircleHelp,
  CloudSun,
  LayoutDashboard,
  Map,
  PanelLeftClose,
  PanelLeftOpen,
  Sprout,
} from 'lucide-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink, Outlet } from 'react-router-dom';
import { farmQueries } from '../../../api/farm/farm.queries.ts';
import { RouterButton } from '../../../components/common/RouterButton';
import { useAppLayout } from '../hooks/useAppLayout.ts';
import { getWorkspaceClassName } from '../utils/workspace.ts';

const { Sider, Content } = Layout;

export function AppLayout() {
  const { handle, active, collapsed, setCollapsed } = useAppLayout();
  const { t, i18n } = useTranslation();
  const { data: preferences } = useSuspenseQuery(farmQueries.profile());
  useEffect(() => {
    if (preferences.language !== i18n.resolvedLanguage) {
      void i18n.changeLanguage(preferences.language);
    }
  }, [preferences.language, i18n]);
  const mainItems = [
    {
      key: '/',
      label: (
        <NavLink to="/" end>
          {t('Overview')}
        </NavLink>
      ),
      icon: <LayoutDashboard size={21} />,
    },
    {
      key: '/map',
      label: <NavLink to="/map">{t('Field map')}</NavLink>,
      icon: <Map size={21} />,
    },
    {
      key: '/fields',
      label: <NavLink to="/fields">{t('My fields')}</NavLink>,
      icon: <Sprout size={21} />,
    },
    {
      key: '/calendar',
      label: <NavLink to="/calendar">{t('Calendar')}</NavLink>,
      icon: <CalendarDays size={21} />,
    },
    {
      key: '/history',
      label: <NavLink to="/history">{t('Environment')}</NavLink>,
      icon: <CloudSun size={21} />,
    },
  ];

  return (
    <Layout className="app-shell">
      <Sider
        id="farm-sidebar"
        className="sidebar"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        width={260}
        breakpoint="lg"
        collapsedWidth={76}
      >
        <div className="sidebar-brand-row">
          <Link to="/" className="brand" aria-label={t('FrogFarmers overview')}>
            <span className="brand-symbol">
              <img src="/frog-farmer.png" width={40} height={40} alt="" />
            </span>
            <span className="brand-word">FrogFarmers</span>
          </Link>
          <Tooltip title={collapsed ? t('Expand sidebar') : t('Collapse sidebar')}>
            <Button
              type="text"
              size="small"
              className="sidebar-collapse"
              aria-label={collapsed ? t('Expand sidebar') : t('Collapse sidebar')}
              aria-expanded={!collapsed}
              aria-controls="farm-sidebar"
              icon={collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
              onClick={() => setCollapsed((current) => !current)}
            />
          </Tooltip>
        </div>
        <Menu mode="inline" selectedKeys={[active]} items={mainItems} />
        <div className="sidebar-bottom">
          <Menu
            mode="inline"
            selectedKeys={[active]}
            items={[
              {
                key: '/notifications',
                label: <NavLink to="/notifications">{t('Notifications')}</NavLink>,
                icon: (
                  <Badge dot color="#b8954d">
                    <Bell size={21} />
                  </Badge>
                ),
              },
              {
                key: '/help',
                label: <NavLink to="/help">{t('Help & resources')}</NavLink>,
                icon: <CircleHelp size={21} />,
              },
            ]}
          />
          <RouterButton
            type="text"
            className="profile"
            to="/settings"
            icon={<Avatar size={28}>{preferences.initials}</Avatar>}
            aria-label={preferences.fullName}
          >
            <span className="sidebar-label">
              <strong>{preferences.fullName}</strong>
            </span>
          </RouterButton>
        </div>
      </Sider>
      <Layout className="workspace">
        <Content className={getWorkspaceClassName(handle.workspace)}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
