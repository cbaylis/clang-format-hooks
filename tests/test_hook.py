# Copyright (C) 2018 Marco Barisione
# Copyright (C) 2018 Undo Ltd.

import os
import subprocess
import unittest

import data

from testutils import (
    WorkDir,
    )

from mixin_scripts_repo import (
    ScriptsRepoMixin,
    CloneRepoMixin,
    SubmoduleMixin,
    CopiedFilesMixin,
    )

class HookTestCaseBase(ScriptsRepoMixin):
    '''
    Test the git hook script.
    '''

    KEY_CONFIG_INTERATIVE = 'hooks.clangFormatDiffInteractive'
    KEY_CONFIG_STYLE = 'hooks.clangFormatDiffStyle'

    def hook_call(self, *args):
        assert self.repo
        return self.repo.check_call(os.path.join('.', self.pre_commit_hook_path), *args)

    def hook_output(self, *args):
        assert self.repo
        return self.repo.check_output(os.path.join('.', self.pre_commit_hook_path), *args)

    def config_set(self, key, value):
        assert self.repo
        return self.repo.check_output('git', 'config', key, value)

    def install(self, allow_errors=False):
        try:
            return True, self.hook_output('install')
        except subprocess.CalledProcessError as exc:
            if not allow_errors:
                raise
            return False, exc.output

    def test_install(self):
        res, output = self.install()
        self.assertTrue(res)
        self.assertEqual(output.strip(), 'Pre-commit hook installed.')

    def test_install_twice(self):
        self.install()

        res, output = self.install(allow_errors=True)
        self.assertFalse(res)
        self.assertEqual(output.strip(), 'The hook is already installed.')

    def test_install_already_exists(self):
        self.repo.write_file(os.path.join('.git', 'hooks', 'pre-commit'), '')

        res, _ = self.install(allow_errors=True)
        self.assertFalse(res)
        #self.assertEqual(output.strip(),
        #                 'There\'s already an existing pre-commit hook, but for something else.')

    def test_commit_no_errors(self):
        self.install()

        self.repo.write_file(data.FILENAME, data.FIXED)
        self.repo.add(data.FILENAME)

        self.repo.commit()

    def test_commit_fix_errors(self):
        self.install()

        self.repo.write_file(data.FILENAME, data.CODE)
        self.repo.add(data.FILENAME)

        old_head = self.repo.git_get_head()

        output = self.repo.commit(input_text='a\n')
        # We don't check for data.PATCH as colordiff may add escapes.
        self.assertIn('before formatting', self.simplify_diff(output))
        self.assertIn('The staged content is not formatted correctly.\n', output)
        self.assertIn('patching file {}'.format(data.FILENAME), output)
        self.assertEqual(output.count('What would you like to do?'), 1)

        # The file on disk is updated.
        self.assertEqual(self.repo.read_file(data.FILENAME), data.FIXED)
        # There was a commit.
        self.assertNotEqual(old_head, self.repo.git_get_head())
        # The commit contains the fixed file.
        commit_diff = self.simplify_diff(self.repo.git_show())
        self.assertIn(data.FIXED_COMMIT, commit_diff)

    def test_commit_force(self):
        self.install()

        self.repo.write_file(data.FILENAME, data.CODE)
        self.repo.add(data.FILENAME)

        old_head = self.repo.git_get_head()

        output = self.repo.commit(input_text='f\n')
        self.assertEqual(output.count('What would you like to do?'), 1)
        self.assertIn('Will commit anyway!', output)
        self.assertIn('Press return to continue.', output)

        # The file on disk is unchanged.
        self.assertEqual(self.repo.read_file(data.FILENAME), data.CODE)
        # There was a commit.
        self.assertNotEqual(old_head, self.repo.git_get_head())
        # The commit contains the original non-fixed file.
        commit_diff = self.simplify_diff(self.repo.git_show())
        self.assertIn(data.NON_FIXED_COMMIT, commit_diff)

    def test_commit_cancel(self):
        self.install()

        self.repo.write_file(data.FILENAME, data.CODE)
        self.repo.add(data.FILENAME)

        old_head = self.repo.git_get_head()

        try:
            self.repo.commit(input_text='c\n')
            self.assertTrue(False)
        except subprocess.CalledProcessError as exc:
            output = exc.output

        self.assertEqual(output.count('What would you like to do?'), 1)
        self.assertIn('Commit aborted as requested.', output)

        # The file on disk is unchanged.
        self.assertEqual(self.repo.read_file(data.FILENAME), data.CODE)
        # There is no commit.
        self.assertEqual(old_head, self.repo.git_get_head())

    def test_commit_non_interactive(self):
        self.install()
        self.config_set(self.KEY_CONFIG_INTERATIVE, 'false')

        self.repo.write_file(data.FILENAME, data.CODE)
        self.repo.add(data.FILENAME)
        with self.assertRaises(subprocess.CalledProcessError):
            self.repo.commit()

        # The file on disk is unchanged.
        self.assertEqual(self.repo.read_file(data.FILENAME), data.CODE)

    def test_commit_no_verify(self):
        self.install()

        self.repo.write_file(data.FILENAME, data.CODE)
        self.repo.add(data.FILENAME)

        old_head = self.repo.git_get_head()
        self.repo.commit(verify=False)

        # The file on disk is unchanged.
        self.assertEqual(self.repo.read_file(data.FILENAME), data.CODE)
        # There was a commit.
        self.assertNotEqual(old_head, self.repo.git_get_head())
        # The commit contains the original non-fixed file.
        commit_diff = self.simplify_diff(self.repo.git_show())
        self.assertIn(data.NON_FIXED_COMMIT, commit_diff)

    def test_commit_style(self):
        self.install()
        self.config_set(self.KEY_CONFIG_STYLE, 'WebKit')

        self.repo.write_file(data.FILENAME, data.CODE)
        self.repo.add(data.FILENAME)

        output = self.repo.commit(input_text='a\n')
        self.assertIn('The staged content is not formatted correctly.\n', output)

        # The file on disk is updated using the specified style.
        self.assertEqual(self.repo.read_file(data.FILENAME), data.FIXED_WEBKIT)

    def test_install_from_scripts_dir(self):
        with self.repo.work_dir():
            # We go into the directory where the scripts are and intall from there.
            # This is particularly interesting in case of submodules as we need to install a hook
            # for the outer repository.
            with WorkDir(self.scripts_dir):
                subprocess.check_output(['./git-pre-commit-format', 'install'],
                                        stderr=subprocess.STDOUT,
                                        universal_newlines=True)

            # Everything should still work.
            self.repo.write_file(data.FILENAME, data.CODE)
            self.repo.add(data.FILENAME)

            output = self.repo.commit(input_text='a\n')
            self.assertIn('The staged content is not formatted correctly.\n', output)

            # The file on disk is updated.
            self.assertEqual(self.repo.read_file(data.FILENAME), data.FIXED)



class HookClonedTestCase(CloneRepoMixin,
                         HookTestCaseBase,
                         unittest.TestCase):
    pass


class HookSubmoduleTestCase(SubmoduleMixin,
                            HookTestCaseBase,
                            unittest.TestCase):
    pass


class HookCopiedScriptsTestCase(CopiedFilesMixin,
                                HookTestCaseBase,
                                unittest.TestCase):
    pass
