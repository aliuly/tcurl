#!/usr/bin/env python3
'''
Credential collection using Urwid with password masking
Equivalent to dialog --form but with modern curses features
Colors match the classic dialog blue theme
'''

import argparse
import os
import pathlib
import subprocess
import sys
import urwid
from urwid.command_map import Command

try:
  from icecream import ic
except ImportError:  # Graceful fallback if IceCream isn't installed.
  ic = lambda *a: None if not a else (a[0] if len(a) == 1 else a)  # noqa - returns None if no args, single arg if one, tuple otherwise

VERSION = '2026.05-DEV'

# Map Tab/Shift+Tab to focus movement between form fields
urwid.command_map['tab'] = Command.DOWN
urwid.command_map['shift tab'] = Command.UP


class FormPile(urwid.Pile):
  '''Pile that treats Enter like Tab on edit fields.'''

  def keypress(self, size, key):
    if key == 'enter':
      # If focus is on an edit field, treat Enter like Tab
      if self._focus_is_edit():
        key = 'tab'
    return super().keypress(size, key)

  def _focus_is_edit(self):
    '''Check if the current focus chain ends at an Edit widget.'''
    w = self.focus
    if w is None:
      return False
    # Unwrap decorations
    while isinstance(w, urwid.WidgetDecoration):
      w = w.original_widget
    # Columns containing an edit field?
    if isinstance(w, urwid.Columns) and w.focus_position is not None:
      child = w.contents[w.focus_position][0]
      while isinstance(child, urwid.WidgetDecoration):
        child = child.original_widget
      return isinstance(child, urwid.Edit)
    return isinstance(w, urwid.Edit)

# Classic Linux dialog color scheme
# Screen background is blue, dialog box interior is cyan
PALETTE = [
    ('body',        'white',      'light blue'),
    ('title',       'white',      'light blue',  'bold'),
    ('prompt',      'yellow',     'light blue'),
    ('edit',        'black',      'white'),
    ('edit_focus',  'white',      'black'),
    ('button',      'white',      'dark green',  'bold'),
    ('button_focus','black',      'yellow'),
    ('error',       'light red',  'light blue'),
]


class CredentialForm:
  '''Urwid form for collecting credentials with masking'''

  def __init__(self, defaults:dict[str,str]|None = None):
    self.result = None
    if defaults is None: defaults = dict()

    # Raw Edit widgets (unwrapped) for value access
    self.username_input = urwid.Edit(
      edit_text=  (defaults.get('username')
                    or os.environ.get('OS_USERNAME')
                    or os.environ.get('USER')
                    or os.environ.get('LOGNAME', '')
                    or ''
                ),
      allow_tab=False,
    )
    self.password_input = urwid.Edit(mask='*',
      allow_tab=False,
      edit_text = (defaults.get('password')
                    or os.environ.get('OS_PASSWORD')
                    or ''
                ),
    )
    self.domain_input = urwid.Edit(
      edit_text = (
          defaults.get('user_domain_name')
          or os.environ.get('OS_USER_DOMAIN_NAME', '')
          or ''
      ),
      allow_tab=False,
    )
    self.otp_input = urwid.Edit(allow_tab=False)

    # OTP status message (shown for OTP warnings and form errors)
    self.otp_status = urwid.Text('')

    # Live OTP validation: only digits allowed, empty is OK
    urwid.connect_signal(self.otp_input, 'postchange', self._on_otp_change)

    # Build labeled fields with separate label/edit styling
    fields = []
    for label_text, edit_widget in [
        ('Username:', self.username_input),
        ('Password:', self.password_input),
        ('Domain:',   self.domain_input),
        ('OTP (optional):', self.otp_input),
    ]:
        label = urwid.AttrMap(
            urwid.Text(f' {label_text} ', align='right'), 'prompt'
        )
        edit = urwid.AttrMap(edit_widget, 'edit', 'edit_focus')
        field = urwid.Columns([(18, label), edit], focus_column=1)
        fields.append(field)

    # Create buttons with dialog styling
    self.submit_button = urwid.Button('Submit', on_press=self.on_submit, align='center')
    self.cancel_button = urwid.Button('Cancel', on_press=self.on_cancel, align='center')

    # Apply button style
    self.submit_button = urwid.AttrMap(self.submit_button, 'button', 'button_focus')
    self.cancel_button = urwid.AttrMap(self.cancel_button, 'button', 'button_focus')

    # Build the form layout
    title_widget = urwid.AttrMap(
      urwid.Text('🔐 Authentication Required', align='center'),
      'title'
    )

    self.form_widgets = FormPile([
      title_widget,
      urwid.Divider(),
    ])
    # Add each field with a divider before it (except the first)
    for i, field in enumerate(fields):
        if i > 0:
            self.form_widgets.contents.append((urwid.Divider(), self.form_widgets.options()))
        self.form_widgets.contents.append((field, self.form_widgets.options()))
        # Add OTP status message right after the OTP field
        if i == 3:  # OTP is the 4th field (index 3)
            self.form_widgets.contents.append((
                urwid.AttrMap(self.otp_status, 'error'),
                self.form_widgets.options()
            ))
    # Add buttons row
    self.form_widgets.contents.append((urwid.Divider(), self.form_widgets.options()))
    # Button row: centered with at least 2-char spacing on sides
    # focus_column=2 so Tab lands on Submit (skip spacers)
    self.form_widgets.contents.append((
        urwid.Columns([
            ('weight', 1, urwid.Text('')),  # flexible left
            (2, urwid.Text('')),             # minimum 2 chars left
            ('pack', self.submit_button),
            (2, urwid.Text('')),             # between buttons
            ('pack', self.cancel_button),
            (2, urwid.Text('')),             # minimum 2 chars right
            ('weight', 1, urwid.Text('')),  # flexible right
        ], focus_column=2),
        self.form_widgets.options()
    ))

    # Store reference to the button row for escape handling
    self._button_row = self.form_widgets.contents[-1][0]

    # Auto-focus the username field (index 2 = title(0), divider(1), username(2))
    self.form_widgets.focus_position = 2

    # Wrap everything in the body style
    body = urwid.AttrMap(self.form_widgets, 'body')

    # Build the dialog box with border
    dialog_box = urwid.LineBox(
      urwid.Padding(body, align='center', width=50),
      title='Login'
    )

    # Fill the entire screen with blue background (classic dialog style)
    self.frame = urwid.AttrMap(
      urwid.Filler(dialog_box, valign='middle'),
      'body'
    )


  def _on_otp_change(self, widget: urwid.Edit, old_text: str) -> None:
    '''Strip non-digit characters and show a status message'''
    current = widget.get_edit_text()
    if current and not current.isdigit():
      digits_only = ''.join(c for c in current if c.isdigit())
      widget.set_edit_text(digits_only)
      self.otp_status.set_text(' Only digits allowed')
    else:
      # Valid input (empty or all digits) — clear status
      self.otp_status.set_text('')

  def on_submit(self, button: urwid.Button) -> None:
    '''Handle form submission'''
    username = self.username_input.get_edit_text()
    password = self.password_input.get_edit_text()
    domain = self.domain_input.get_edit_text()
    otp = self.otp_input.get_edit_text()

    # Validation
    errors = []
    if not username:
      errors.append('Username required')
    if not password:
      errors.append('Password required')
    if not domain:
      errors.append('Domain required')

    if errors:
      # Show validation error in the status area
      error_text = '\n'.join(errors)
      self.otp_status.set_text(f' {error_text}')
      return

    # Store credentials and exit
    self.result = {
      'username': username,
      'password': password,
      'domain': domain,
      'otp': otp if otp else None
    }
    raise urwid.ExitMainLoop()

  def on_cancel(self, button: urwid.Button) -> None:
    '''Handle form cancellation'''
    self.result = None
    raise urwid.ExitMainLoop()

  def run(self) -> Optional[Dict]:
    '''Run the form and return credentials'''

    def unhandled(key: str) -> bool:
      '''Handle Escape key for field clearing and Cancel focus.'''
      if key == 'esc':
        return self._handle_escape()
      return False

    # Always send urwid output to stderr so the TUI works even when
    # stdout is redirected (e.g. piped to a file).
    screen = urwid.raw_display.Screen(output=sys.stderr)

    self.loop = urwid.MainLoop(self.frame, palette=PALETTE, unhandled_input=unhandled, screen=screen)
    self.loop.run()
    return self.result

  def _handle_escape(self) -> bool:
    '''Clear the current edit field or focus the Cancel button.'''
    # Walk the focus chain to find the Edit widget
    w = self.form_widgets.focus
    if w is None:
      return False
    while isinstance(w, urwid.WidgetDecoration):
      w = w.original_widget
    edit = None
    if isinstance(w, urwid.Columns) and w.focus_position is not None:
      child = w.contents[w.focus_position][0]
      while isinstance(child, urwid.WidgetDecoration):
        child = child.original_widget
      if isinstance(child, urwid.Edit):
        edit = child
    if edit is None:
      return False

    if edit.get_edit_text():
      # Field has content → clear it
      edit.set_edit_text('')
    else:
      # Field is empty → focus Cancel button
      # The button row is a Columns; set its focus to Cancel (column 4)
      self._button_row.focus_position = 4
      # Move the Pile's focus to the button row (last item)
      self.form_widgets.focus_position = len(self.form_widgets.contents) - 1
    return True


def get_credentials(defaults:dict[str,str]|None = None) -> dict[str,str]|None:
  '''
  Show credential form and return results

  Returns:
    Dictionary with 'username', 'password', 'domain', 'otp' keys,
    or None if cancelled
  '''
  form = CredentialForm(defaults)
  return form.run()

def parser_factory(color:bool = False) -> argparse.ArgumentParser:
  '''Create and configure the command-line argument parser.

  :return: Configured argument parser
  '''
  if sys.version_info >= (3,14):
    color = { 'color': color }
  else:
    color = dict()

  parser = argparse.ArgumentParser(
    prog='tcurl-login',
    description='Enter authentication details and issue temporary token',
    fromfile_prefix_chars='@',
    allow_abbrev=True,
    **color,
  )
  parser.add_argument('--version', '-V', action='version', version=VERSION)
  xscope = parser.add_mutually_exclusive_group()
  xscope.add_argument('--project','-p',
                    default = None,
                    help = 'Scope the token to the given project')
  xscope.add_argument('--region', '-R',
                    default = None,
                    help='Unscoped token for the given region')
  parser.add_argument('--auth-url','-A',
                  dest = 'auth_url',
                  default = None,
                  help = 'Auth URL (or environment OS_AUTH_URL)')
  parser.add_argument('--tcurl','-s',
                  help= 'path to tcurl script')
  parser.add_argument('--format','-f',
                  default = 'shell',
                  choices = ['raw','json','shell','yaml'],
                  help = 'Output format')
  parser.add_argument('--output','-o',
                  default = None,
                  type = pathlib.Path,
                  help= 'path to tcurl script')

  return parser

def main():
  parser = parser_factory(color = True)
  args = parser.parse_args()
  ic(args)

  if args.tcurl:
    if not args.tcurl.startswith('/'):
      if os.path.isfile(os.path.join(os.getcwd(),args.tcurl)):
        args.tcurl = os.path.join(os.getcwd(),args.tcurl)
      else:
        for d in os.getenv('PATH',''):
          if os.path.isdir(d) and os.path.isfile(os.path.join(d,args.tcurl)):
            args.tcurl = os.path.join(d,args.tcurl)
            break
        else:
          raise FileNotFoundError(args.tcurl)
    elif not os.path.isfile(args.tcurl):
      raise FileNotFoundError(args.tcurl)
    if not os.access(args.tcurl,os.X_OK):
      cmd = [ 'python3', args.tcurl ]
    ic(args.tcurl)
  else:
    rc = subprocess.run(['sh','-c','type tcurl'])
    if rc.returncode: exit(36)
    cmd = [ 'tcurl' ] # Assume it is just a command in the path

  cmd.extend(['login','-i'])
  if args.project is not None: cmd.extend(['--project', args.project])
  if args.region is not None: cmd.extend(['--region', args.region])
  if args.auth_url is not None: cmd.extend(['--auth-url', args.auth_url])
  cmd.extend(['--format',args.format])
  ic(cmd)

  creds = get_credentials()
  if creds:
    sys.stderr.write(f'Log in...{" ".join(cmd)}\n')
    rc = subprocess.run(cmd,
                        input = (
                            f'{creds["username"]}\n'
                            f'{creds["password"]}\n'
                            f'{creds["domain"]}\n'
                            f'{creds["otp"] if creds["otp"] else ""}\n'
                          ),
                        capture_output = True,
                        text = True)
    sys.stderr.write(rc.stderr)
    if not rc.stderr.endswith('\n'): sys.stderr.write('\n')
    if rc.returncode == 0:
      if args.output is None:
        print(rc.stdout)
      else:
        with open(args.output,'w') as fp:
          fp.write(rc.stdout)
    else:
      exit(rc.returncode)
  else:
    sys.stderr.write('\n❌ Authentication cancelled\n')
    exit(31)

if __name__ == '__main__':
  main()
