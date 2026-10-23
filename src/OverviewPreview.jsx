import { overviewIcon } from "./overview-icons.js";

function Icon({name}) {
  // The markup is a fixed local icon; uploaded content never enters this HTML.
  return <span className="previewIcon" dangerouslySetInnerHTML={{__html: overviewIcon(name)}} />;
}

export function OverviewPreview({openAccount}) {
  return <>
    <aside id="previewSidebar" className="previewSidebar" aria-label="Preview workspace" hidden>
      <a className="previewBrand" href="#overview-preview" aria-label="AI Business Insights overview">
        <span className="previewBrandMark" aria-hidden="true"><i /><i /><i /></span>
        <span>AI Business<br /> Insights</span>
      </a>
      <p className="previewNavLabel">WORKSPACE</p>
      <nav className="previewNavigation" aria-label="Preview dashboard navigation">
        <a href="#overview-preview" aria-current="page"><Icon name="dashboard" />Overview</a>
        <a href="#detailed-dashboard"><Icon name="charts" />Detailed dashboard</a>
        <button id="previewInsights" type="button"><Icon name="insights" />At a glance</button>
        <button id="previewAiSettings" type="button" aria-haspopup="dialog"><Icon name="sparkles" />AI settings</button>
      </nav>
      <div className="previewSidebarBottom">
        <div className="previewDatasetInfo">
          <span className="previewDatasetLabel"><Icon name="dataset" />CURRENT DATASET</span>
          <strong id="previewSidebarDataset">Choose a dataset</strong>
          <p>Your data, in perspective.<br />Keep your original file.</p>
        </div>
        <button id="previewChangeDataset" type="button"><Icon name="upload" />Change dataset</button>
        <a className="previewOriginalLink" href="#business-overview"><Icon name="back" />Original overview</a>
      </div>
    </aside>
    <div id="previewHeader" className="previewHeader" hidden>
      <div className="previewHeading">
        <h1>AI Business Insights</h1>
        <p>Turn your data into a clearer picture of your business.</p>
      </div>
      <div className="previewHeaderActions">
        <button id="previewFilterButton" type="button" aria-expanded="false" aria-controls="dashboardFilters"><Icon name="filter" />Filters<span id="previewFilterCount" hidden /></button>
        <button id="previewCustomize" type="button" aria-haspopup="dialog"><Icon name="settings" />Customize</button>
        {openAccount && <button className="previewAccountButton" type="button" onClick={openAccount} aria-haspopup="dialog" aria-label="Manage your account"><Icon name="account" /></button>}
      </div>
    </div>
  </>;
}
