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
        const mode = {'#business-overview': 'overviewMode', '#detailed-dashboard': 'detailMode', '#overview-preview': 'previewMode'}[hash];
        return mode && document.body.classList.contains(mode);
    }''', arg=href)


def check_header(page):
    header = page.locator('#previewHeader:visible, .dashboardHeader:visible')
    box = header.bounding_box()
    assert box and abs(box['height'] - 72) < 1, box
    if not page.locator('body').evaluate("el => el.classList.contains('previewMode')"):
        assert abs(box['y']) < 1, box
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Header causes horizontal overflow'


def check_menu(page, expect):
    preview = page.locator('body').evaluate("el => el.classList.contains('previewMode')")
    menu_id = 'previewPageMenu' if preview else 'pageMenu'
    trigger, menu = page.locator('#' + menu_id + 'Button'), page.locator('#' + menu_id)
    trigger.focus()
    page.keyboard.press('Enter')
    expect(menu).to_be_visible()
    expect(trigger).to_have_attribute('aria-expanded', 'true')
    expect(menu.locator('a')).to_have_count(5)
    assert menu.evaluate('el => el.contains(document.activeElement)')
    page.keyboard.press('Escape')
    expect(menu).to_be_hidden()
    expect(trigger).to_be_focused()
    trigger.click()
    page.mouse.click(24, 24)
    expect(menu).to_be_hidden()
