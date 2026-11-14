import { Hand, LassoSelect, PenTool, Plus, ScanLine } from 'lucide-react';

export const mapGuideSteps = [
  {
    id: 'move',
    icon: Hand,
    title: 'Find your fields',
    instructions: [
      'Select Move map (the hand icon), then drag to your area. Scroll or pinch to zoom, or click a numbered cluster to zoom into that group.',
      'Keep zooming until you see individual field dots. Hover over a dot to see its name and approximate area. The drawing tools become available once the dots have loaded.',
    ],
    demoDescription: 'The map pans, then a numbered cluster opens to reveal individual field dots.',
  },
  {
    id: 'lasso',
    icon: LassoSelect,
    title: 'Draw with the lasso',
    instructions: [
      'Choose Lasso selection. Press and drag around the field dots you want, then release to close the outline and create a draft section.',
      'In Lasso mode, click an individual field dot to toggle its selection. Press Esc to abandon an unfinished outline and return to Move map.',
    ],
    demoDescription:
      'The lasso traces around three field dots and an Add button appears inside the section.',
  },
  {
    id: 'points',
    icon: PenTool,
    title: 'Draw with points',
    instructions: [
      'For a straight-sided outline, choose Point selection. Click at least three corners around the field dots you want, then click the first corner again to close the shape.',
      'On a keyboard, press Backspace to undo the last point, Enter to close the outline, or Esc to abandon it.',
    ],
    demoDescription:
      'The cursor places four corners, then returns to the first corner to close the section.',
  },
  {
    id: 'analyze',
    icon: ScanLine,
    title: 'Analyze the section',
    instructions: [
      'Click Add inside the outline to open Section overview. Check the selected field count and approximate area, then click Analyze.',
      'Wait for the map to find field boundaries and classify crops. If you drew the wrong section, use Cancel section and draw it again.',
    ],
    demoDescription:
      'Add opens the section panel. Analyze starts a progress bar and the map reveals the predicted crop areas.',
  },
  {
    id: 'save',
    icon: Plus,
    title: 'Review and save crop areas',
    instructions: [
      'Click a crop icon on the map to include or exclude that area. Use the checkbox next to a crop in Section overview to select or clear all areas of that crop.',
      'Check the selected area count, then click Add areas to save your selection. The section closes once the save succeeds.',
    ],
    demoDescription:
      'A map icon and a crop checkbox change which areas are selected before Add areas saves the remaining selection.',
  },
] as const;

export const mapGuideQuestions = [
  {
    id: 'imagery',
    question: 'Why does the map look different from the crop prediction?',
    answer:
      'The satellite basemap comes from an imagery provider and may show an older capture. FieldSense uses newer available Sentinel-2 observations to predict what is growing. A different crop, harvest, or change to the field can therefore appear in the prediction before it appears on the basemap.',
  },
  {
    id: 'zoom',
    question: 'Why are the drawing tools disabled?',
    answer:
      'The lasso and point tools need individual field dots to be visible. Click a numbered cluster or zoom in, then wait for the field dots to load.',
  },
  {
    id: 'add',
    question: 'What is the difference between Add and Add areas?',
    answer:
      'Add opens the draft section so you can review and analyze it. Add areas saves the crop areas you kept after analysis. Cancel section discards the draft.',
  },
  {
    id: 'skipped',
    question: 'Why were some fields skipped during analysis?',
    answer:
      'The tool needs a usable field boundary and enough clear satellite observations to classify a crop. If areas are skipped, review the remaining results or retry with a smaller section around the fields you need.',
  },
] as const;
