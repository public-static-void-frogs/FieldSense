const cropImages = new Map([
  ['Corn', 'corn.jpg'],
  ['Soybeans', 'soybeans.jpg'],
  ['Alfalfa', 'alfalfa.jpg'],
  ['Grassland/Pasture', 'pasture.jpg'],
  ['Winter wheat', 'winter-wheat.jpg'],
]);

type CropIllustrationProps = { crop: string | null };

export function CropIllustration({ crop }: CropIllustrationProps) {
  const filename = cropImages.get(crop ?? '') ?? 'pasture.jpg';

  return (
    <img
      className="crop-field-illustration"
      src={`${import.meta.env.BASE_URL}crops/${filename}`}
      alt=""
      width={480}
      height={384}
      loading="lazy"
      decoding="async"
    />
  );
}
