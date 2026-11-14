import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { FarmlandBackdrop } from '../../../components/common/FarmlandBackdrop';
import { LegalLinks } from '../../legal/components/LegalLinks.tsx';
import { LoginForm } from './LoginForm.tsx';
import { RegistrationForm } from './RegistrationForm.tsx';
import '../../legal/components/legal.css';
import '../../../styles/login.css';

type AuthPageProps = { register?: boolean };

export function AuthPage({ register = false }: AuthPageProps) {
  const { t } = useTranslation();
  const { search } = useLocation();
  const heading = register ? t('Create account') : t('Log in');

  return (
    <main className="login-page">
      <FarmlandBackdrop />
      <div className="login-corner-brand" aria-hidden="true">
        <img src="/frog-farmer.png" width={32} height={32} alt="" />
        <span>FrogFarmers</span>
      </div>
      <section
        className={`login-clearing ${register ? 'registration-clearing' : ''}`}
        aria-labelledby="login-heading"
      >
        <div className="login-brand">
          <img src="/frog-farmer.png" width={64} height={64} alt="" />
          <span>FrogFarmers</span>
        </div>
        <h1 id="login-heading">{heading}</h1>
        {register ? <RegistrationForm /> : <LoginForm />}
        <p className="login-demo-note">
          <Link to={`${register ? '/login' : '/register'}${search}`}>
            {register ? t('Already have an account? Log in') : t('Create an account')}
          </Link>
        </p>
        <LegalLinks />
      </section>
    </main>
  );
}
