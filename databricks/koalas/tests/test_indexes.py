#
# Copyright (C) 2019 Databricks, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from distutils.version import LooseVersion
import inspect

import numpy as np
import pandas as pd
import pyspark

import databricks.koalas as ks
from databricks.koalas.exceptions import PandasNotImplementedError
from databricks.koalas.missing.indexes import _MissingPandasLikeIndex, _MissingPandasLikeMultiIndex
from databricks.koalas.testing.utils import ReusedSQLTestCase, TestUtils


class IndexesTest(ReusedSQLTestCase, TestUtils):

    @property
    def pdf(self):
        return pd.DataFrame({
            'a': [1, 2, 3, 4, 5, 6, 7, 8, 9],
            'b': [4, 5, 6, 3, 2, 1, 0, 0, 0],
        }, index=[0, 1, 3, 5, 6, 8, 9, 9, 9])

    @property
    def kdf(self):
        return ks.from_pandas(self.pdf)

    def test_index(self):
        for pdf in [pd.DataFrame(np.random.randn(10, 5), index=list('abcdefghij')),
                    pd.DataFrame(np.random.randn(10, 5),
                                 index=pd.date_range('2011-01-01', freq='D', periods=10)),
                    pd.DataFrame(np.random.randn(10, 5),
                                 columns=list('abcde')).set_index(['a', 'b'])]:
            if LooseVersion(pyspark.__version__) < LooseVersion('2.4'):
                # PySpark < 2.4 does not support struct type with arrow enabled.
                with self.sql_conf({'spark.sql.execution.arrow.enabled': False}):
                    kdf = ks.from_pandas(pdf)
                    self.assert_eq(kdf.index, pdf.index)
            else:
                kdf = ks.from_pandas(pdf)
                self.assert_eq(kdf.index, pdf.index)

    def test_index_getattr(self):
        kidx = self.kdf.index
        item = 'databricks'

        expected_error_message = ("'Index' object has no attribute '{}'".format(item))
        with self.assertRaisesRegex(AttributeError, expected_error_message):
            kidx.__getattr__(item)

    def test_multi_index_getattr(self):
        arrays = [[1, 1, 2, 2], ['red', 'blue', 'red', 'blue']]
        idx = pd.MultiIndex.from_arrays(arrays, names=('number', 'color'))
        pdf = pd.DataFrame(np.random.randn(4, 5), idx)
        kdf = ks.from_pandas(pdf)
        kidx = kdf.index
        item = 'databricks'

        expected_error_message = ("'MultiIndex' object has no attribute '{}'".format(item))
        with self.assertRaisesRegex(AttributeError, expected_error_message):
            kidx.__getattr__(item)

    def test_to_series(self):
        pidx = self.pdf.index
        kidx = self.kdf.index

        self.assert_eq(kidx.to_series(), pidx.to_series())
        self.assert_eq(kidx.to_series(name='a'), pidx.to_series(name='a'))

        pidx = self.pdf.set_index('b', append=True).index
        kidx = self.kdf.set_index('b', append=True).index

        if LooseVersion(pyspark.__version__) < LooseVersion('2.4'):
            # PySpark < 2.4 does not support struct type with arrow enabled.
            with self.sql_conf({'spark.sql.execution.arrow.enabled': False}):
                self.assert_eq(kidx.to_series(), pidx.to_series())
                self.assert_eq(kidx.to_series(name='a'), pidx.to_series(name='a'))
        else:
            self.assert_eq(kidx.to_series(), pidx.to_series())
            self.assert_eq(kidx.to_series(name='a'), pidx.to_series(name='a'))

    def test_index_names(self):
        kdf = self.kdf
        self.assertIsNone(kdf.index.name)

        idx = pd.Index([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], name='x')
        pdf = pd.DataFrame(np.random.randn(10, 5), idx)
        kdf = ks.from_pandas(pdf)

        self.assertEqual(kdf.index.name, pdf.index.name)
        self.assertEqual(kdf.index.names, pdf.index.names)

        pidx = pdf.index
        kidx = kdf.index
        pidx.name = 'renamed'
        kidx.name = 'renamed'
        self.assertEqual(kidx.name, pidx.name)
        self.assertEqual(kidx.names, pidx.names)
        self.assert_eq(kidx, pidx)

        with self.assertRaisesRegex(ValueError, "Names must be a list-like"):
            kidx.names = 'hi'

        expected_error_message = ("Length of new names must be {}, got {}"
                                  .format(len(kdf._internal.index_map), len(['0', '1'])))
        with self.assertRaisesRegex(ValueError, expected_error_message):
            kidx.names = ['0', '1']

    def test_multi_index_names(self):
        arrays = [[1, 1, 2, 2], ['red', 'blue', 'red', 'blue']]
        idx = pd.MultiIndex.from_arrays(arrays, names=('number', 'color'))
        pdf = pd.DataFrame(np.random.randn(4, 5), idx)
        kdf = ks.from_pandas(pdf)

        self.assertEqual(kdf.index.names, pdf.index.names)

        pidx = pdf.index
        kidx = kdf.index
        pidx.names = ['renamed_number', 'renamed_color']
        kidx.names = ['renamed_number', 'renamed_color']
        self.assertEqual(kidx.names, pidx.names)
        if LooseVersion(pyspark.__version__) < LooseVersion('2.4'):
            # PySpark < 2.4 does not support struct type with arrow enabled.
            with self.sql_conf({'spark.sql.execution.arrow.enabled': False}):
                self.assert_eq(kidx, pidx)
        else:
            self.assert_eq(kidx, pidx)

        with self.assertRaises(PandasNotImplementedError):
            kidx.name
        with self.assertRaises(PandasNotImplementedError):
            kidx.name = 'renamed'

    def test_missing(self):
        kdf = ks.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6], 'c': [7, 8, 9]})

        # Index functions
        missing_functions = inspect.getmembers(_MissingPandasLikeIndex, inspect.isfunction)
        unsupported_functions = [name for (name, type_) in missing_functions
                                 if type_.__name__ == 'unsupported_function']
        for name in unsupported_functions:
            with self.assertRaisesRegex(
                    PandasNotImplementedError,
                    "method.*Index.*{}.*not implemented( yet\\.|\\. .+)".format(name)):
                getattr(kdf.set_index('a').index, name)()

        deprecated_functions = [name for (name, type_) in missing_functions
                                if type_.__name__ == 'deprecated_function']
        for name in deprecated_functions:
            with self.assertRaisesRegex(PandasNotImplementedError,
                                        "method.*Index.*{}.*is deprecated".format(name)):
                getattr(kdf.set_index('a').index, name)()

        # MultiIndex functions
        missing_functions = inspect.getmembers(_MissingPandasLikeMultiIndex, inspect.isfunction)
        unsupported_functions = [name for (name, type_) in missing_functions
                                 if type_.__name__ == 'unsupported_function']
        for name in unsupported_functions:
            with self.assertRaisesRegex(
                    PandasNotImplementedError,
                    "method.*Index.*{}.*not implemented( yet\\.|\\. .+)".format(name)):
                getattr(kdf.set_index(['a', 'b']).index, name)()

        deprecated_functions = [name for (name, type_) in missing_functions
                                if type_.__name__ == 'deprecated_function']
        for name in deprecated_functions:
            with self.assertRaisesRegex(PandasNotImplementedError,
                                        "method.*Index.*{}.*is deprecated".format(name)):
                getattr(kdf.set_index(['a', 'b']).index, name)()

        # Index properties
        missing_properties = inspect.getmembers(_MissingPandasLikeIndex,
                                                lambda o: isinstance(o, property))
        unsupported_properties = [name for (name, type_) in missing_properties
                                  if type_.fget.__name__ == 'unsupported_property']
        for name in unsupported_properties:
            with self.assertRaisesRegex(
                    PandasNotImplementedError,
                    "property.*Index.*{}.*not implemented( yet\\.|\\. .+)".format(name)):
                getattr(kdf.set_index('a').index, name)

        deprecated_properties = [name for (name, type_) in missing_properties
                                 if type_.fget.__name__ == 'deprecated_property']
        for name in deprecated_properties:
            with self.assertRaisesRegex(PandasNotImplementedError,
                                        "property.*Index.*{}.*is deprecated".format(name)):
                getattr(kdf.set_index('a').index, name)

        # MultiIndex properties
        missing_properties = inspect.getmembers(_MissingPandasLikeMultiIndex,
                                                lambda o: isinstance(o, property))
        unsupported_properties = [name for (name, type_) in missing_properties
                                  if type_.fget.__name__ == 'unsupported_property']
        for name in unsupported_properties:
            with self.assertRaisesRegex(
                    PandasNotImplementedError,
                    "property.*Index.*{}.*not implemented( yet\\.|\\. .+)".format(name)):
                getattr(kdf.set_index(['a', 'b']).index, name)

        deprecated_properties = [name for (name, type_) in missing_properties
                                 if type_.fget.__name__ == 'deprecated_property']
        for name in deprecated_properties:
            with self.assertRaisesRegex(PandasNotImplementedError,
                                        "property.*Index.*{}.*is deprecated".format(name)):
                getattr(kdf.set_index(['a', 'b']).index, name)

    def test_multi_index_not_supported(self):
        kdf = ks.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6], 'c': [7, 8, 9]})

        with self.assertRaisesRegex(TypeError,
                                    "cannot perform any with this index type"):
            kdf.set_index(['a', 'b']).index.any()

        with self.assertRaisesRegex(TypeError,
                                    "cannot perform all with this index type"):
            kdf.set_index(['a', 'b']).index.all()
