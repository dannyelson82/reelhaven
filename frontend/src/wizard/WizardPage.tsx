// The setup wizard (ADR-0026): from a folder to automatic compression, one step at a time.
import { Card, Stack, Stepper, Text, Title } from '@mantine/core';
import { useSearchParams } from 'react-router';
import { FolderStep, LanguagesStep, ScanStep, type StepProps } from './LibrarySteps';

interface Step {
  key: string;
  label: string;
  component: (props: StepProps) => React.ReactNode;
}

const COMING_NEXT: Step = {
  key: 'next',
  label: 'Size and quality',
  component: () => (
    <Text>The next steps (size and quality, audio, a test run and going automatic) come next.</Text>
  ),
};

/** The steps for this run: a new library starts at the folder. */
function wizardSteps(newLibrary: boolean): Step[] {
  return [
    ...(newLibrary ? [{ key: 'folder', label: 'Folder', component: FolderStep }] : []),
    { key: 'scan', label: 'Read files', component: ScanStep },
    { key: 'languages', label: 'Languages', component: LanguagesStep },
    COMING_NEXT,
  ];
}

export function WizardPage() {
  const [params, setParams] = useSearchParams();
  const library = params.get('library');
  const libraryId = library ? Number(library) : null;
  // A library that existed before the wizard opened skips the folder step.
  const steps = wizardSteps(params.get('new') === '1' || libraryId === null);
  const current = Math.max(
    0,
    steps.findIndex((s) => s.key === params.get('step')),
  );
  const go = (index: number, id: number | null = libraryId) => {
    const next = new URLSearchParams(params);
    if (id !== null) next.set('library', String(id));
    if (libraryId === null && id !== null) next.set('new', '1');
    next.set('step', steps[index].key);
    setParams(next, { replace: true });
  };
  const Step = steps[current].component;

  return (
    <Stack maw={860}>
      <Title order={2}>Set up automatic compression</Title>
      <Stepper active={current} size="sm" allowNextStepsSelect={false}>
        {steps.map((s) => (
          <Stepper.Step key={s.key} label={s.label} />
        ))}
      </Stepper>
      <Card withBorder padding="lg">
        <Step
          libraryId={libraryId}
          onNext={(id) => go(Math.min(current + 1, steps.length - 1), id ?? libraryId)}
          onBack={current > 0 ? () => go(current - 1) : undefined}
        />
      </Card>
    </Stack>
  );
}
