// The download is bound to the selected retained study across headers, jobs and bytes.
export function packBindingMatches(study, binding) {
  return Boolean(binding?.study && binding?.revision && binding?.project
    && study?.study_sha256 === binding.study && study.specification?.revision_sha256 === binding.revision
    && study.specification?.project_id === binding.project);
}
export function createReviewPackDownloader({readContext, isContext, readStudy, fetchPack, waitJob, save, setState}) {
  let serial = 0;
  function invalidate(message = 'Select a retained study to download its review pack.') {++serial; setState('idle', message);}
  async function download() {
    const id = ++serial, context = readContext(), selected = readStudy();
    const binding = {project: selected?.specification?.project_id, study: selected?.study_sha256, revision: selected?.specification?.revision_sha256};
    const current = () => id === serial && isContext(context) && packBindingMatches(readStudy(), binding);
    const ensureCurrent = () => {if (!current()) throw new Error('Study or workspace changed. Download the selected study again.');};
    try {
      if (!packBindingMatches(selected, binding)) throw new Error('Select a retained study first.');
      setState('pending', 'Preparing the selected study’s PDF and verified review pack…');
      let response = await fetchPack(binding); ensureCurrent();
      if (response.status === 202) {
        const job = await response.json(); ensureCurrent();
        if (typeof job.job_id !== 'string' || !job.job_id || job.kind !== 'report' || job.project_id !== binding.project) throw new Error('Review pack preparation job identity differs from the selected project.');
        if (JSON.parse(job.spec_json).study_sha256 !== binding.study) throw new Error('Report job belongs to a different retained study.');
        await waitJob(job, current); ensureCurrent(); response = await fetchPack(binding); ensureCurrent();
      }
      if (response.status !== 200) throw new Error('Review pack is not ready. Try again after its report job completes.');
      const header = key => response.headers.get(key);
      if (header('X-Project-ID') !== binding.project || header('X-Review-Pack-Schema') !== 'study_review_pack_v1' || header('X-Study-SHA256') !== binding.study || header('X-Revision-SHA256') !== binding.revision || header('Content-Type')?.split(';')[0] !== 'application/zip') throw new Error('Review pack identity or format differs from the selected study.');
      const expected = header('X-Pack-SHA256');
      if (!/^[a-f0-9]{64}$/.test(expected || '')) throw new Error('Review pack checksum is missing.');
      const bytes = await response.arrayBuffer(); ensureCurrent();
      if (bytes.byteLength > 41 * 1024 * 1024) throw new Error('Review pack download exceeds its file budget.');
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(n => n.toString(16).padStart(2, '0')).join(''); ensureCurrent();
      if (hash !== expected) throw new Error('Review pack checksum differs from the downloaded bytes.');
      save(new Blob([bytes], {type: 'application/zip'}), 'study-review-' + binding.study + '.zip');
      setState('downloaded', 'Review pack download requested. File checksum verified; engineering approval remains as recorded.');
    } catch (error) {
      if (id === serial && isContext(context)) setState('failed', 'Review pack unavailable: ' + error.message);
      throw error;
    }
  }
  return {invalidate, download};
}