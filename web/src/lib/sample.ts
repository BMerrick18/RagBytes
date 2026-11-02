export const SAMPLE_DOCUMENT = { url: "/sample-report.docx", name: "Harbour lighting trial.docx" };

export async function loadSampleDocument(): Promise<File> {
  const response = await fetch(SAMPLE_DOCUMENT.url);
  if (!response.ok) throw new Error(`Couldn't load the sample report (${response.status}).`);
  const blob = await response.blob();
  return new File([blob], SAMPLE_DOCUMENT.name, { type: blob.type });
}
