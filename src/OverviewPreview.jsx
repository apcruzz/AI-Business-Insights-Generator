import { overviewIcon } from "./overview-icons.js";
import { HeaderNavigation } from "./HeaderNavigation.jsx";

function Icon({name}) {
  // The markup is a fixed local icon; uploaded content never enters this HTML.
  return <span className="previewIcon" dangerouslySetInnerHTML={{__html: overviewIcon(name)}} />;
}

export function OverviewPreview({user}) {
  return <>
    <aside id="previewSidebar" className="previewSidebar" aria-label="Workspace navigation" hidden>
      <a className="previewBrand" href="#business-overview" aria-label="AI Business Insights overview">
        <span className="previewBrandMark" aria-hidden="true"><i /><i /><i /></span>
        <span>AI Business<br /> Insights</span>
      </a>
      <p className="previewNavLabel">WORKSPACE</p>
      <nav className="previewNavigation" aria-label="Dashboard navigation">
        <a href="#business-overview"><Icon name="dashboard" />Business overview</a>
        <a href="#detailed-dashboard"><Icon name="charts" />Detailed dashboard</a>
        <a href="#account"><Icon name="account" />Account</a>
        <button id="previewAiSettings" type="button" aria-haspopup="dialog"><Icon name="sparkles" />AI settings</button>
      </nav>
      <div className="previewSidebarBottom">
        <div className="previewDatasetInfo">
          <span className="previewDatasetLabel"><Icon name="dataset" />CURRENT DATASET</span>
          <strong id="previewSidebarDataset">Choose a dataset</strong>
          <p>Your data, in perspective.<br />Keep your original file.</p>
        </div>
        <button id="previewChangeDataset" data-workspace-page="#change-dataset" type="button"><Icon name="upload" />Change dataset</button>
      </div>
    </aside>
    <button id="sidebarToggle" className="sidebarToggle" type="button" aria-controls="previewSidebar" aria-expanded="true" aria-label="Collapse sidebar" title="Collapse sidebar">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m14 7-5 5 5 5" /></svg>
    </button>
    <div id="previewHeader" className="previewHeader" hidden>
      <div className="previewHeading">
        <h1 id="businessOverviewTitle">Business overview</h1>
        <p>Turn your data into a clearer picture of your business.</p>
      </div>
      <div className="previewHeaderActions">
        <button id="previewFilterButton" type="button" aria-expanded="false" aria-controls="dashboardFilters"><Icon name="filter" />Filters<span id="previewFilterCount" hidden /></button>
        <button id="previewCustomize" type="button" aria-haspopup="dialog"><Icon name="settings" />Customize</button>
        <HeaderNavigation preview user={user} />
      </div>
    </div>
  </>;
}
