import './CropIcon.css';

const cropIcons = [
  { code: 1, label: 'Corn', image: 'corn.svg' },
  { code: 2, label: 'Cotton', image: 'cotton.svg' },
  { code: 3, label: 'Rice', image: 'rice.svg' },
  { code: 4, label: 'Sorghum', image: 'sorghum.svg' },
  { code: 5, label: 'Soybeans', image: 'soybeans.svg' },
  { code: 23, label: 'Spring Wheat', image: 'spring-wheat.svg' },
  { code: 24, label: 'Winter Wheat', image: 'winter-wheat.svg' },
  { code: 27, label: 'Rye', image: 'rye.svg' },
  { code: 28, label: 'Oats', image: 'oats.svg' },
  { code: 36, label: 'Alfalfa', image: 'alfalfa.svg' },
  { code: 37, label: 'Other Hay/Non Alfalfa', image: 'hay.svg' },
  { code: 61, label: 'Fallow/Idle Cropland', image: 'fallow.svg' },
  { code: 62, label: 'Pasture/Grass', image: 'pasture.svg' },
  { code: 83, label: 'Water', image: 'water.svg' },
  { code: 111, label: 'Open Water', image: 'water.svg' },
  { code: 141, label: 'Deciduous Forest', image: 'deciduous-forest.svg' },
  { code: 176, label: 'Grassland/Pasture', image: 'pasture.svg' },
] as const;

function normalizeCropLabel(label: string) {
  return label.toLowerCase().replace(/[^a-z0-9]/g, '');
}

type CropIconProps = {
  crop: string | number | null | undefined;
  size?: number;
};

export function CropIcon({ crop, size = 24 }: CropIconProps) {
  const cropKey = typeof crop === 'string' ? normalizeCropLabel(crop) : crop;
  const icon = cropIcons.find(({ code, label }) =>
    typeof cropKey === 'number' ? code === cropKey : normalizeCropLabel(label) === cropKey,
  );

  return (
    <img
      className="crop-icon"
      src={`${import.meta.env.BASE_URL}crop-icons/${icon?.image ?? 'generic.svg'}`}
      width={size}
      height={size}
      alt=""
    />
  );
}
