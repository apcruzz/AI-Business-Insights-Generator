"""Navigation shared by the optional browser checks."""


def navigate(page, nav_id):
    menu = 'previewPageMenu' if page.locator('body').evaluate("el => el.classList.contains('previewMode')") else 'pageMenu'
    if not page.locator('#' + menu).is_visible():
        page.locator('#' + menu + 'Button').click()
    link = page.locator('#' + ('preview' if menu == 'previewPageMenu' else '') + nav_id)
    href = link.get_attribute('href')
    link.click()
    page.wait_for_url('**/' + href)
    page.wait_for_function('''hash => {
        const visible = id => !document.getElementById(id).hidden;
        if (hash === '#account') return visible('accountPage');
        if (hash === '#change-dataset') return visible('setupPage');
        if (visible('setupPage') && !visible('dashboardMain')) return true;
        const mode = {'#business-overview': 'previewMode', '#detailed-dashboard': 'detailMode'}[hash];
        return mode && document.body.classList.contains(mode);
    }''', arg=href)


def check_header(page):
    header = page.locator('#previewHeader:visible, .dashboardHeader:visible')
    box = header.bounding_box()
    assert box and abs(box['height'] - 72) < 1, box
    if not page.locator('body').evaluate("el => el.classList.contains('previewMode')"):
        # The shared mobile brand bar precedes the sticky header until scrolling.
        max_top = page.locator('#previewSidebar').bounding_box()['height'] if page.viewport_size['width'] <= 760 else 0
        assert -.5 <= box['y'] <= max_top + 1, box
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Header causes horizontal overflow'
    sidebar = page.locator('#previewSidebar').bounding_box()
    assert sidebar, 'All workspace pages share the preview navigation shell'
    if page.viewport_size['width'] > 760:
        collapsed = page.locator('body').evaluate("el => el.classList.contains('sidebarCollapsed')")
        assert abs(box['x'] - (0 if collapsed else sidebar['width'])) < 1, {'header': box, 'sidebar': sidebar}
    assert header.evaluate('el => getComputedStyle(el).backgroundColor') == 'rgb(247, 248, 252)'


def check_menu(page, expect):
    preview = page.locator('body').evaluate("el => el.classList.contains('previewMode')")
    menu_id = 'previewPageMenu' if preview else 'pageMenu'
    trigger, menu = page.locator('#' + menu_id + 'Button'), page.locator('#' + menu_id)
    trigger.focus()
    page.keyboard.press('Enter')
    expect(menu).to_be_visible()
    expect(trigger).to_have_attribute('aria-expanded', 'true')
    expect(menu.locator('a')).to_have_count(4)
    assert menu.evaluate('el => el.contains(document.activeElement)')
    page.keyboard.press('Escape')
    expect(menu).to_be_hidden()
    expect(trigger).to_be_focused()
    trigger.click()
    page.mouse.click(1, page.viewport_size['height'] - 1)
    expect(menu).to_be_hidden()


def check_form_alignment(page, selector):
    """Form controls keep the shared size and fit their cards on narrow screens."""
    controls = page.locator(selector).locator('input:visible:not([type="checkbox"]):not([type="radio"]), select:visible')
    sizes = controls.evaluate_all('''els => els.map(el => {
        const box = el.getBoundingClientRect();
        return {id: el.id, x: box.x, right: box.right, height: box.height};
    })''')
    target = 32 if page.viewport_size['width'] <= 760 else 36
    for control in sizes:
        assert -.5 <= control['x'] and control['right'] <= page.viewport_size['width'] + .5, control
        assert abs(control['height'] - target) < 1, control
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
