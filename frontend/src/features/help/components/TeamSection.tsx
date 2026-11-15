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
            'We are a five-frog team from Ukraine with experience in building high-load production systems, powered with large scale data and machine learning pipelines. We’ve competed in several hackathons, so we know how to scope tightly, split work cleanly and ship a working demo under pressure. Our strength is turning large, messy datasets into tools people can actually use. We care about validation as much as speed: we test our models against real data and are upfront about what they can and can’t do.',
          )}
        </Typography.Paragraph>
      </header>
      <div className="team-grid">
        {team.map((frog) => (
          <Card
            key={frog.id}
            className="team-card"
            cover={
              <div className="team-portrait-frame">
                <img
                  className="team-portrait"
                  src={`/images/team/${frog.id}.webp`}
                  alt={frog.alt}
                  width={768}
                  height={512}
                  decoding="async"
                />
                <img
                  className="team-portrait-badge"
                  src="/images/team/chatgpt.svg"
                  alt={t('Made with ChatGPT')}
                  title={t('Made with ChatGPT')}
                  width={30}
                  height={30}
                />
              </div>
            }
          >
            <Typography.Title level={4}>{frog.name}</Typography.Title>
            <Typography.Paragraph>{frog.roles}</Typography.Paragraph>
            <Typography.Link
              href={frog.linkedin}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={t('{{name}} on LinkedIn', { name: frog.name })}
            >
              LinkedIn
            </Typography.Link>
          </Card>
        ))}
      </div>
    </section>
  );
}
