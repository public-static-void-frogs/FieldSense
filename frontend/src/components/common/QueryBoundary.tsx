import { Button, Result } from 'antd';
import type { ReactNode } from 'react';
import { Component } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { isUnauthorized } from '../../features/auth/utils/auth.ts';
import { useTranslation } from 'react-i18next';
import { ApiUnavailableError } from '../../api/core/http.ts';
import { ApiUnavailablePage } from '../../pages/ApiUnavailablePage.tsx';

type QueryBoundaryProps = {
  children: ReactNode;
  onReset: () => void;
};

type QueryBoundaryState = {
  error: Error | null;
};

export class QueryBoundary extends Component<QueryBoundaryProps, QueryBoundaryState> {
  state: QueryBoundaryState = { error: null };
  static getDerivedStateFromError(error: Error): QueryBoundaryState {
    return { error };
  }
  retry = () => {
    this.props.onReset();
    this.setState({ error: null });
  };
  render() {
    if (isUnauthorized(this.state.error)) {
      return <SessionExpired />;
    }
    if (this.state.error instanceof ApiUnavailableError) {
      return <ApiUnavailablePage retry={this.retry} />;
    }
    return this.state.error ? <QueryError retry={this.retry} /> : this.props.children;
  }
}

type QueryErrorProps = {
  retry: () => void;
};

function QueryError({ retry }: QueryErrorProps) {
  const { t } = useTranslation();

  return (
    <Result
      status="error"
      title={t('Unable to load data')}
      subTitle={t('Please try again.')}
      extra={
        <Button type="primary" onClick={retry}>
          {t('Try again')}
        </Button>
      }
    />
  );
}

function SessionExpired() {
  const { pathname, search } = useLocation();

  return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />;
}
