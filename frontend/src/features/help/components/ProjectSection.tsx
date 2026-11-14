import { Card, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { FarmlandBackdrop } from '../../../components/common/FarmlandBackdrop';

export function ProjectSection() {
  const { t } = useTranslation();

  return (
    <section
      className="team-garden project-garden"
      id="about-the-project"
      aria-labelledby="project-heading"
    >
      <FarmlandBackdrop />
      <header className="team-intro">
        <Typography.Title level={1} id="project-heading">
          {t('About the project')}
        </Typography.Title>
        <Typography.Paragraph>
          {t(
            'FrogFarmers is a decision-support prototype for exploring crop rotations at field level. It brings field locations, soil and crop information, environmental history, and rotation recommendations into one place, so farmers can compare strategies and review the actions each one proposes.',
          )}
        </Typography.Paragraph>
      </header>
      <Card title={t('About the Challenge')} className="project-information">
        <Typography.Paragraph>
          {t(
            'Farmers around the world navigate shifting temperatures, changing rainfall patterns, water shortages, extreme weather, and declining soil health. These pressures make it difficult to choose crop rotations that protect fields, conserve water, and support long-term resilience. Your challenge is to create a decision-support tool that uses NASA Earth observations along with local soil information, crop characteristics, and farmer priorities to help farmers explore rotation strategies that could strengthen soil health and adapt their farms to changing conditions.',
          )}
        </Typography.Paragraph>
      </Card>
      <div className="project-problem-solution">
        <Card title={t('The problem')} className="project-information">
          <Typography.Paragraph>
            {t(
              'A crop that worked well last season may be less suitable as rainfall, soil moisture, and nutrient availability change. Farmers need to weigh those conditions together, understand the trade-offs between rotations, and decide when to prepare, plant, irrigate, or reassess.',
            )}
          </Typography.Paragraph>
        </Card>
        <Card title={t('Our solution')} className="project-information">
          <Typography.Paragraph>
            {t(
              'The proposed workflow combines NASA Earth observations with local soil data, crop characteristics, and farmer priorities to support field-specific rotation strategies. Each strategy explains its inputs, compares current and projected conditions, and proposes actions that farmers can review before adding the schedule to their calendar.',
            )}
          </Typography.Paragraph>
          <Typography.Paragraph>
            {t('This demo illustrates the workflow with sample field data and predictions.')}
          </Typography.Paragraph>
        </Card>
      </div>
    </section>
  );
}
