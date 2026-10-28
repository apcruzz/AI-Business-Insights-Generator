import { useRef, useState } from "react";
import { overviewIcon } from "./overview-icons.js";

// Route hashes are handled by dashboard.js; keeping this list shared makes both headers agree.
const pages = [
  ["overviewNav", "#business-overview", "Business Overview"],
  ["detailNav", "#detailed-dashboard", "Detailed Dashboard"],
  ["previewNav", "#overview-preview", "Overview preview"],
  ["setupNav", "#change-dataset", "Change dataset"],
  ["accountNav", "#account", "Account"],
];

export function HeaderNavigation({preview = false, user}) {
  const menu = useRef(null), [open, setOpen] = useState(false);
  // Both headers stay mounted, so their popover targets and link IDs must remain distinct.
  const menuId = preview ? "previewPageMenu" : "pageMenu";
  return <div className="headerNavigation">
    <a id={preview ? "previewAccountButton" : "accountButton"} className="headerAccountLink" href="#account" aria-label="Your account" title={user?.displayName || user?.username || "Your account"}>
      {/* This SVG comes from the fixed icon registry, never from an uploaded cell or account name. */}
      <span aria-hidden="true" dangerouslySetInnerHTML={{__html: overviewIcon("account")}} />
    </a>
    <button id={`${menuId}Button`} className="pageMenuButton" type="button" popoverTarget={menuId} aria-label="Open navigation" aria-expanded={open} aria-controls={menuId}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
    </button>
    <nav id={menuId} className="pageMenu" popover="auto" ref={menu} aria-label="Workspace pages" onToggle={event => {
      // Native dismissal also fires toggle, keeping aria-expanded correct after Escape or outside clicks.
      const opened = event.newState === "open";
      setOpen(opened);
      // Move keyboard focus into the page links instead of leaving it on the menu button.
      if (opened) menu.current.querySelector('[aria-current="page"], a')?.focus();
    }}>
      <p className="pageMenuLabel">YOUR WORKSPACE</p>
      {pages.map(([id, href, label]) => <a id={preview ? `preview${id}` : id} key={id} href={href} onClick={() => menu.current.hidePopover()}>{label}</a>)}
    </nav>
  </div>;
}
