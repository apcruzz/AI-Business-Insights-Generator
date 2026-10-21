import { useEffect, useRef, useState } from "react";
import "./accounts.css";

async function accountRequest(path, {method = "GET", body, token} = {}) {
  let response;
  try {
    response = await fetch(path, {method, credentials: "same-origin", cache: "no-store",
      headers: body ? {"Content-Type": "application/json", "X-Dashboard-Token": token || ""} : {},
      body: body ? JSON.stringify(body) : undefined});
  } catch {
    throw Error("Could not reach the account service. Check your connection and try again.");
  }
  const value = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = Error(value.error || "The account service is unavailable. Try again shortly.");
    error.status = response.status;
    throw error;
  }
  return value;
}

export function AccountAccess({children}) {
  const [session, setSession] = useState(null);
  const [error, setError] = useState("");
  const [accountOpen, setAccountOpen] = useState(false);
  const load = async () => {
    setError("");
    try { setSession(await accountRequest("/api/auth/session")); }
    catch (error) { setError(error.message); }
  };
  useEffect(() => {
    load();
    const refreshRestoredPage = event => { if (event.persisted) window.location.reload(); };
    window.addEventListener("pageshow", refreshRestoredPage);
    return () => window.removeEventListener("pageshow", refreshRestoredPage);
  }, []);
  if (!session) return <main className="authPage"><section className="authCard"><p className="authEyebrow">BUSINESS INSIGHTS</p><h1>{error ? "Connection interrupted" : "Opening your workspace…"}</h1>{error && <><p className="authError" role="alert">{error}</p><button className="authPrimary" onClick={load}>Try again</button></>}</section></main>;
  if (!session.authenticated) return <SignIn session={session} onSignedIn={() => window.location.reload()} />;
  const accounts = session.authMode === "accounts";
  return <>{children({openAccount: accounts ? () => setAccountOpen(true) : null})}
    {accounts && accountOpen && <AccountDialog session={session} onClose={() => setAccountOpen(false)} />}
  </>;
}

function SignIn({session, onSignedIn}) {
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    setError("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    if (registering && values.password !== values.confirmPassword) { setError("Passwords do not match."); return; }
    delete values.confirmPassword;
    setBusy(true);
    try {
      await accountRequest(registering ? "/api/auth/register" : "/api/auth/login", {method: "POST", body: values, token: session.token});
      await onSignedIn();
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  };
  return <main className="authPage">
    <div className="authIntroduction">
      <p className="authEyebrow">AI BUSINESS INSIGHTS</p>
      <h1>Your data.<br />A clearer picture.</h1>
      <p>Turn your spreadsheets into useful dashboards and conversations.</p>
      <div className="authFeatures"><span>Interactive dashboards</span><span>Groq or your own local Ollama</span><span>Your own workspace</span></div>
    </div>
    <section className="authCard" aria-labelledby="authTitle">
      <div className="authTabs" role="group" aria-label="Account access">
        <button type="button" aria-pressed={!registering} disabled={busy} onClick={() => {setRegistering(false); setError("");}}>Sign in</button>
        {session.registrationOpen && <button type="button" aria-pressed={registering} disabled={busy} onClick={() => {setRegistering(true); setError("");}}>Create account</button>}
      </div>
      <h2 id="authTitle">{registering ? "Create your account" : "Welcome back"}</h2>
      <p className="authDescription">{registering ? "Choose a username and a password to get started." : "Sign in to build your business dashboard."}</p>
      <form className="accountForm" id="authForm" method="post" onSubmit={submit} key={String(registering)}>
        {registering && <label htmlFor="registerDisplayName"><span>Display name <span className="optionalLabel">optional</span></span><input id="registerDisplayName" name="displayName" autoComplete="nickname" maxLength={80} /></label>}
        <label htmlFor="authUsername">Username<input id="authUsername" name="username" autoComplete="username" autoCapitalize="none" spellCheck="false" required minLength={registering ? 3 : undefined} maxLength={32} pattern={registering ? "[A-Za-z0-9][A-Za-z0-9_.\\-]{2,31}" : undefined} aria-describedby={registering ? "usernameHelp" : undefined} /></label>
        {registering && <small id="usernameHelp">3–32 letters, numbers, dots, underscores or hyphens.</small>}
        <label htmlFor="authPassword">Password<input id="authPassword" name="password" type="password" autoComplete={registering ? "new-password" : "current-password"} required minLength={registering ? 16 : undefined} maxLength={256} /></label>
        {registering && <><small>At least 16 characters. A long, unique passphrase works well.</small><label htmlFor="confirmRegistrationPassword">Confirm password<input id="confirmRegistrationPassword" name="confirmPassword" type="password" autoComplete="new-password" required minLength={16} maxLength={256} /></label></>}
        {error && <p className="authError" role="alert">{error}</p>}
        <button className="authPrimary" id="authSubmit" disabled={busy}>{busy ? "Please wait…" : registering ? "Create account" : "Sign in"}</button>
      </form>
      <p className="authFootnote">Keep your original files. Uploaded datasets and conversations are temporary, and uploads are processed on the server even when you use local Ollama.</p>
      {!session.registrationOpen && <p className="authFootnote">New account registration is currently closed.</p>}
    </section>
  </main>;
}

function AccountDialog({session, onClose}) {
  const dialog = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  useEffect(() => { dialog.current.showModal(); }, []);
  const perform = async (path, method, body) => {
    setBusy(true);
    setError("");
    try {
      await accountRequest(path, {method, body, token: session.token});
      // Remove every previous dataset, transcript, model connection and CSRF token from this page.
      window.location.reload();
    } catch (error) {
      if (error.status === 401) window.location.reload();
      else { setError(error.message); setBusy(false); }
    }
  };
  const update = (event, passwordChange = false) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    if (passwordChange && values.newPassword !== values.confirmPassword) { setError("New passwords do not match."); return; }
    delete values.confirmPassword;
    perform("/api/account", "PATCH", values);
  };
  return <dialog id="accountDialog" className="accountDialog" ref={dialog} aria-labelledby="accountTitle" onClose={onClose}>
    <div className="accountDialogLayout">
      <div className="chooserHeader"><div><h2 id="accountTitle">Your account</h2><p className="sub">Signed in as {session.user.username}</p></div><button className="iconButton" type="button" aria-label="Close account settings" onClick={() => dialog.current.close()}>×</button></div>
      <div className="accountDialogBody">
        <p className="accountChangeNotice">Saving changes signs out other devices and clears your temporary dashboard. Your account will stay registered.</p>
        {error && <p className="authError" role="alert">{error}</p>}
        <section className="accountSection"><h3>Profile</h3>
          <form className="accountForm" id="profileForm" method="post" onSubmit={update}>
            <label htmlFor="profileDisplayName">Display name<input id="profileDisplayName" name="displayName" defaultValue={session.user.displayName} required maxLength={80} autoComplete="nickname" /></label>
            <label htmlFor="profileUsername">Username<input id="profileUsername" name="username" defaultValue={session.user.username} required minLength={3} maxLength={32} autoComplete="username" autoCapitalize="none" spellCheck="false" /></label>
            <label htmlFor="profileCurrentPassword">Current password<input id="profileCurrentPassword" name="currentPassword" type="password" required maxLength={256} autoComplete="current-password" /></label>
            <button className="authPrimary" disabled={busy}>Save profile</button>
          </form>
        </section>
        <section className="accountSection"><h3>Change password</h3>
          <form className="accountForm" id="passwordForm" method="post" onSubmit={event => update(event, true)}>
            <label htmlFor="passwordCurrent">Current password<input id="passwordCurrent" name="currentPassword" type="password" required maxLength={256} autoComplete="current-password" /></label>
            <label htmlFor="passwordNew">New password<input id="passwordNew" name="newPassword" type="password" required minLength={16} maxLength={256} autoComplete="new-password" /></label>
            <label htmlFor="passwordConfirm">Confirm new password<input id="passwordConfirm" name="confirmPassword" type="password" required minLength={16} maxLength={256} autoComplete="new-password" /></label>
            <button className="authPrimary" disabled={busy}>Update password</button>
          </form>
        </section>
        <section className="accountSection accountDanger"><h3>Delete account</h3><p>This permanently removes your account, signs out every device, and clears your temporary datasets and conversations. Creating the same username later will create a new account.</p>
          <form className="accountForm" id="deleteAccountForm" method="post" onSubmit={event => {event.preventDefault(); if (deleteConfirmed) perform("/api/account", "DELETE", Object.fromEntries(new FormData(event.currentTarget)));}}>
            <label htmlFor="deleteCurrentPassword">Current password<input id="deleteCurrentPassword" name="currentPassword" type="password" required maxLength={256} autoComplete="current-password" /></label>
            <label className="confirmDeletion"><input id="confirmAccountDeletion" type="checkbox" checked={deleteConfirmed} onChange={event => setDeleteConfirmed(event.target.checked)} />I understand this permanently deletes my account.</label>
            <button className="dangerButton" disabled={busy || !deleteConfirmed}>Delete my account</button>
          </form>
        </section>
      </div>
      <div className="accountDialogFooter"><small>Joined {new Date(session.user.createdAt).toLocaleDateString()}</small><button id="signOutButton" type="button" disabled={busy} onClick={() => perform("/api/auth/logout", "POST", {})}>Sign out</button></div>
    </div>
  </dialog>;
}
