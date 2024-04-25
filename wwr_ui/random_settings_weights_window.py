from typing import cast
from PySide6.QtGui import *
from PySide6.QtCore import *
from PySide6.QtWidgets import *

from wwr_ui.uic.ui_random_settings_weights_window import Ui_RandomSettingsWeightsWindow

from options.base_options import Option
from options.wwrando_options import Options
from options.randomized.weights import Choice, OptionWeight, format_weight
from options.randomized.weight_sets import WeightSet


class RSWeightsWindow(QDialog):

    STYLESHEET = """
    table { 
        border-collapse: collapse; 
    }
    table tr td {
        border: 1px solid black; 
        border-top: 1px dotted black;
        border-bottom: 1px dotted black;
        padding: 2px;
    }
    table tr td.setting_weight {
        font-weight: bold;
        border-left: 1px solid black;
    }
    table tr td.first {
        border-top: 2px solid black;
        padding-top: 4px;
    }
    table tr td.last {
        border-bottom: 2px solid black;
        padding-bottom: 4px;
    }
    table thead tr th {
        border: 1px solid black;
        border-bottom: 2px solid black;
    }
    table tr td ul.multichoice {
        -qt-list-indent: 0;
        list-style: none;
    }
    table tr td ul.multichoice li {
    }
    table tr td table {
        margin: 0;
        padding: 0;
    }
    table tr td table tr td {
        border: 1px solid black;
    }
"""

    def __init__(self, parent: QWidget | None, preset: str, weights: WeightSet) -> None:
        super().__init__(parent)
        self.ui = Ui_RandomSettingsWeightsWindow()
        self.ui.setupUi(self)

        self.build_weight_table(preset, weights)

    def format_random_settings_choice(self, choice) -> str:
        if isinstance(choice, str) and choice in Options.by_name:
            choice = Options.by_name[choice]

        if isinstance(choice, OptionWeight):
            if len(choice.managed_options) == 1:
                if choice.help_text():
                    choice = f"{self.format_random_settings_choice(choice.managed_options[0])}<br>{choice.help_text()}"
                else:
                    choice = self.format_random_settings_choice(choice.managed_options[0])
            else:
                text = f"<p>{choice.help_text()}</p><ul>"
                for opt in choice.managed_options:
                    text += f"<li>{self.format_random_settings_choice(opt)}</li>"
                text += "</ul>"
                choice = text

        if isinstance(choice, Option):
            text = ""
            if label_for_option := cast(
                QLabel, self.parent().findChild(QLabel, "label_for_" + choice.name)
            ):
                choice = label_for_option.text()
            elif checkbox_option := cast(
                QCheckBox, self.parent().findChild(QCheckBox, choice.name)
            ):
                capitalized_first_word = choice.name.split("_")[0].capitalize()
                if capitalized_first_word in (
                    "Progression",
                    "Randomize",
                ) and not checkbox_option.text().startswith(capitalized_first_word):
                    # Avoid stuttering if the label repeats the word
                    choice = f"{capitalized_first_word} {checkbox_option.text()}"
                else:
                    choice = checkbox_option.text()

        if isinstance(choice, (list, tuple)):
            if len(choice) == 0:
                choice = "None of the options"
            else:
                choice = " & ".join(self.format_random_settings_choice(c) for c in choice)
        if isinstance(choice, dict):
            entries = []
            for opt, value in choice.items():
                if isinstance(value, bool):
                    if value:
                        entries.append(f'<li>{self.format_random_settings_choice(opt)}</li>')
                else:
                    entries.append(f'<li>{self.format_random_settings_choice(opt)}: '
                                    f'{self.format_random_settings_choice(value)}</li>')

            if len(entries) == 0:
                choice = "None of the options"
            else:
                choice = f'<ul class="multichoice">{"".join(entries)}</ul>'

        if isinstance(choice, range) and choice.step == 1:
            # Collapse consecutive ranges of numbers for fewer lines in the output
            return f"{choice[0]} - {choice[-1]} (each)"

        return str(choice)

    @staticmethod
    def _classes_for_index(idx, iterlen):
        css_class = []
        if idx == 0:
            css_class.append("first")
        elif idx == iterlen - 1:
            css_class.append("last")
        return " ".join(css_class)

    def build_weight_table(self, preset: str, weights: WeightSet) -> None:
        self.setWindowTitle(f'Random Settings weights for preset "{preset}"')
        text = f"""
        <h2>{preset}</h2>
        <p>{Options.by_name["random_settings_preset"].choice_descriptions[preset]}</p><br>
        <table><thead><tr>
            <th>Option</th>
            <th>Choices</th>
            <th>Weight</th>
        </tr></thead><tbody>\n
        """

        for line in weights:
            if len(line.display_choices) == 0:
                continue

            text += "<tr>\n"
            # choice is a namedtuple and inherits from tuple, so we can't just check that it's a tuple for nesting
            is_nested = not isinstance(line.display_choices[0], Choice)
            is_toggle = not is_nested and isinstance(line.display_choices[0].choice, bool)  # type: ignore
            option_cell = self.format_random_settings_choice(line)
            text += (
                f'<td valign="middle" '
                f'rowspan="{len(line.display_choices)}" colspan="{2 if is_toggle else 1}" '
                f'class="first last">{option_cell}</td>'
            )

            if is_nested:
                choices = cast(
                    list[tuple[Choice, OptionWeight]],
                    line.display_choices,
                )
                text += f'<td colspan="2" rowspan="{len(choices)}" class="first last"><table>'
                classes = ""
                for bidx, (branch, subline) in enumerate(choices):
                    text += "<tr>"
                    text += f'<td valign="middle" rowspan="{len(subline.display_choices)}" class="{classes}">{self.format_random_settings_choice(branch.choice)}</td>\n'
                    text += f'<td valign="middle" rowspan="{len(subline.display_choices)}" class="setting_weight {classes}">{format_weight(branch.weight)}</td>\n'
                    for idx, optchoice in enumerate(cast(list[Choice], subline.display_choices)):
                        if idx > 0:
                            text += "</tr>\n<tr>"
                        text += f'<td class="{classes}">{self.format_random_settings_choice(optchoice.choice)}</td>\n'
                        text += f'<td valign="middle" class="setting_weight {classes}">{format_weight(optchoice.weight)}</td>\n'
                    text += "</tr>\n"
                text += "</table></td>"
                # Now flush the rest of the non-written rowspan lines
                text += "</tr><tr>\n" * (len(choices) - 1)

            elif is_toggle:
                choice = cast(Choice, line.display_choices[0])
                text += f'<td class="setting_weight first last">{format_weight(choice.weight)}</td>\n'
            else:
                choices = cast(list[Choice], line.display_choices)
                for idx, optchoice in enumerate(choices):
                    # Qt doesn't support nth-child pseudo-selectors so we have to count these manually
                    classes = self._classes_for_index(idx, len(choices))
                    if idx > 0:
                        text += "</tr>\n<tr>"

                    text += f'<td class="{classes}">{self.format_random_settings_choice(optchoice.choice)}</td>\n'
                    text += (
                        f'<td valign="middle" class="setting_weight {classes}">{format_weight(optchoice.weight)}</td>\n'
                    )
            text += "</tr>\n"
        text += "</tbody></table>"
        doc = QTextDocument()
        doc.setDefaultStyleSheet(self.STYLESHEET)
        doc.setHtml(text)
        self.ui.weightsText.setDocument(doc)
