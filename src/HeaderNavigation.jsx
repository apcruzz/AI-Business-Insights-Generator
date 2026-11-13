import { useRef, useState } from "react";
import { overviewIcon } from "./overview-icons.js";

const pages = [
  ["overviewNav", "#business-overview", "Business Overview"],
  ["detailNav", "#detailed-dashboard", "Detailed Dashboard"],
  ["setupNav", "#change-dataset", "Change dataset"],
  ["accountNav", "#account", "Account"],
];

export function HeaderNavigation({preview = false, user}) {
  const menu = useRef(null), [open, setOpen] = useState(false);
  const menuId = preview ? "previewPageMenu" : "pageMenu";
  return <div className="headerNavigation">
    <a id={preview ? "previewAccountButton" : "accountButton"} className="headerAccountLink" href="#account" aria-label="Your account" title={user?.displayName || user?.username || "Your account"}>
      <span aria-hidden="true" dangerouslySetInnerHTML={{__html: overviewIcon("account")}} />
    </a>
    <button id={`${menuId}Button`} className="pageMenuButton" type="button" popoverTarget={menuId} aria-label="Open navigation" aria-expanded={open} aria-controls={menuId}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
    </button>
    <nav id={menuId} className="pageMenu" popover="auto" ref={menu} aria-label="Workspace pages" onToggle={event => {
      const opened = event.newState === "open";
      setOpen(opened);
      if (opened) {
        // Position below the actual trigger, including the mobile brand bar or a scrolled header.
        const button = document.getElementById(`${menuId}Button`);
        const bottom = button.getBoundingClientRect().bottom + 8;
        menu.current.style.top = `${bottom}px`;
        menu.current.style.maxHeight = `${Math.max(100, window.innerHeight - bottom - 12)}px`;
        menu.current.querySelector('[aria-current="page"], a')?.focus();
      }
    }}>
      <p className="pageMenuLabel">YOUR WORKSPACE</p>
      {pages.map(([id, href, label]) => <a id={preview ? `preview${id}` : id} key={id} href={href} onClick={() => menu.current.hidePopover()}>{label}</a>)}
    </nav>
  </div>;
}
