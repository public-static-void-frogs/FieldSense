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
            'FieldSense is a decision-support tool for exploring crop rotations at field level. It brings field locations, soil and crop information, environmental history, and rotation recommendations into one place, so farmers can compare strategies and review the actions each one proposes.',
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
              'Farmers around the world are making rotation decisions under conditions that no longer behave as they used to. Temperatures are shifting, rainfall is less predictable, and water shortages, erosion, nutrient depletion and extreme weather add uncertainty every season. Soil health is declining across many regions.',
            )}
          </Typography.Paragraph>
          <Typography.Paragraph>
            {t(
              'Choosing which crops to add to a rotation has become hard because no crop is good everywhere. A crop that builds soil in one place may use too much water in another, bring in disease, conflict with local markets, or fall outside the expected growing season.',
            )}
          </Typography.Paragraph>
        </Card>
        <Card title={t('Our solution')} className="project-information">
          <Typography.Paragraph>
            {t(
              'We developed a web-based decision-support tool that helps farmers plan crop rotations for a changing climate. It combines NASA Earth observations (such as POWER weather, GPM IMERG rainfall, SMAP soil moisture, HLS v2.0 imagery and NEX-GDDP-CMIP6 climate projections etc.) with other sources like ESA Sentinel-1 radar, the USDA Cropland Data Layer and USDA soil surveys and more.',
            )}
          </Typography.Paragraph>
          <Typography.Paragraph>
            {t(
              'Our tool enables farmers to explore real-time and historical metrics of each field. Machine-learning and statistical models provide real-time analysis of each field’s health and several rotation strategies for consideration.',
            )}
          </Typography.Paragraph>
          <Typography.Paragraph>
            {t(
              'An SI assistant makes our tool customisable for user’s priorities and constraints and interpretable for people with any level of technical or geospatial experience, explaining each strategy’s benefits, evidence, gaps and risks. It supports farmers’ judgment and local expertise, not replaces them.',
            )}
          </Typography.Paragraph>
        </Card>
      </div>
    </section>
  );
}
