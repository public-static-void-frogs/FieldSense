import { useSuspenseQuery } from '@tanstack/react-query';
import { Card, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { helpQueries } from '../../../api/help/help.queries.ts';
import { FarmlandBackdrop } from '../../../components/common/FarmlandBackdrop';

export function TeamSection() {
  const { t } = useTranslation();
  const { data: team } = useSuspenseQuery(helpQueries.team());

  return (
    <section className="team-garden" id="about-the-team" aria-labelledby="team-heading">
      <FarmlandBackdrop />
      <header className="team-intro">
        <Typography.Title level={1} id="team-heading">
          {t('About the team')}
        </Typography.Title>
        <Typography.Paragraph>
          {t(
            'We are a six-frog team from Ukraine. We’ve competed in several hackathons, so we know how to scope tightly, split work cleanly and ship a working demo under pressure. Our strength is turning large, messy datasets into tools people can actually use. We care about validation as much as speed: we test our models against real data and are upfront about what they can and can’t do.',
          )}
        </Typography.Paragraph>
      </header>
      <div className="team-grid">
        {team.map((frog) => (
          <Card
            key={frog.id}
            className="team-card"
            cover={
              <img
                className="team-portrait"
                src={`/images/team/${frog.id}.webp`}
                alt={frog.alt}
                width={768}
                height={512}
                decoding="async"
              />
            }
          >
            <Typography.Title level={4}>{frog.name}</Typography.Title>
            <Typography.Paragraph>{frog.roles}</Typography.Paragraph>
          </Card>
        ))}
      </div>
    </section>
  );
}
