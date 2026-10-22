// Only the HttpOnly cookie retains access. The workspace token is used once at sign-in.
let publicAccess = false;
async function session(method = 'GET', token) {
  const response = await fetch('/api/session', {
    method, credentials: 'same-origin', cache: 'no-store',
    headers: token === undefined ? {} : {Authorization: 'Bearer ' + token},
    signal: AbortSignal.timeout(15000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Connection failed: ' + response.status);
  publicAccess = data.public_access === true;
  return data.connected;
}
export const isPublicAccess = () => publicAccess;
export const restoreSession = () => session();
export const connectSession = token => session('POST', token);
export const forgetSession = () => session('DELETE');
