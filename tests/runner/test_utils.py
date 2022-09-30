#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import unittest
from typing import Iterator, Union
from unittest.mock import MagicMock

from torch import nn
from torchtnt.runner.callback import Callback
from torchtnt.runner.progress import Progress
from torchtnt.runner.state import EntryPoint, State
from torchtnt.runner.unit import (
    EvalUnit,
    PredictUnit,
    TEvalData,
    TPredictData,
    TrainUnit,
    TTrainData,
)
from torchtnt.runner.utils import (
    _is_done,
    _is_epoch_done,
    _reset_module_training_mode,
    _run_callback_fn,
    _set_module_training_mode,
    _step_requires_iterator,
)
from torchtnt.utils import Timer


class UtilsTest(unittest.TestCase):
    def test_set_module_training_mode(self) -> None:
        """
        Test _set_module_training_mode
        """
        module = nn.Linear(1, 1)
        loss_fn = nn.CrossEntropyLoss()

        tracked_modules = {"module": module, "loss_fn": loss_fn}

        # set module training mode to False
        prior_module_train_states = _set_module_training_mode(tracked_modules, False)

        self.assertFalse(module.training)
        self.assertFalse(loss_fn.training)

        self.assertTrue(prior_module_train_states["module"])
        self.assertTrue(prior_module_train_states["loss_fn"])

        # set back to True
        prior_module_train_states = _set_module_training_mode(tracked_modules, True)

        self.assertTrue(module.training)
        self.assertTrue(loss_fn.training)

        self.assertFalse(prior_module_train_states["module"])
        self.assertFalse(prior_module_train_states["loss_fn"])

    def test_reset_module_training_mode(self) -> None:
        """
        Test _reset_module_training_mode
        """
        module = nn.Linear(1, 1)
        loss_fn = nn.CrossEntropyLoss()

        tracked_modules = {"module": module, "loss_fn": loss_fn}

        # set module training mode to False
        prior_module_train_states = _set_module_training_mode(tracked_modules, False)

        self.assertFalse(module.training)
        self.assertFalse(loss_fn.training)

        # set back to True using reset
        _reset_module_training_mode(tracked_modules, prior_module_train_states)

        self.assertTrue(module.training)
        self.assertTrue(loss_fn.training)

    def test_run_callback_fn_hooks(self) -> None:
        """
        Test _run_callback_fn with all of the hooks on Callback
        """
        callback = DummyCallback("train")
        train_unit = MagicMock()
        timer = Timer()
        dummy_train_state = State(
            entry_point=EntryPoint.TRAIN,
            timer=timer,
            train_state=None,
        )
        self.assertEqual(callback.dummy_data, "train")

        _run_callback_fn(
            [callback],
            "on_exception",
            dummy_train_state,
            train_unit,
            ValueError("test"),
        )
        self.assertEqual(callback.dummy_data, "on_exception")
        self.assertTrue(
            "callback.DummyCallback.on_exception" in timer.recorded_durations.keys()
        )

        _run_callback_fn([callback], "on_train_start", dummy_train_state, train_unit)
        self.assertEqual(callback.dummy_data, "on_train_start")
        self.assertTrue(
            "callback.DummyCallback.on_train_start" in timer.recorded_durations.keys()
        )

        _run_callback_fn(
            [callback], "on_train_epoch_start", dummy_train_state, train_unit
        )
        self.assertEqual(callback.dummy_data, "on_train_epoch_start")
        self.assertTrue(
            "callback.DummyCallback.on_train_epoch_start"
            in timer.recorded_durations.keys()
        )

        _run_callback_fn(
            [callback], "on_train_step_start", dummy_train_state, train_unit
        )
        self.assertEqual(callback.dummy_data, "on_train_step_start")
        self.assertTrue(
            "callback.DummyCallback.on_train_step_start"
            in timer.recorded_durations.keys()
        )

        _run_callback_fn([callback], "on_train_step_end", dummy_train_state, train_unit)
        self.assertEqual(callback.dummy_data, "on_train_step_end")
        self.assertTrue(
            "callback.DummyCallback.on_train_step_end"
            in timer.recorded_durations.keys()
        )

        _run_callback_fn(
            [callback], "on_train_epoch_end", dummy_train_state, train_unit
        )
        self.assertEqual(callback.dummy_data, "on_train_epoch_end")
        self.assertTrue(
            "callback.DummyCallback.on_train_epoch_end"
            in timer.recorded_durations.keys()
        )

        _run_callback_fn([callback], "on_train_end", dummy_train_state, train_unit)
        self.assertEqual(callback.dummy_data, "on_train_end")
        self.assertTrue(
            "callback.DummyCallback.on_train_end" in timer.recorded_durations.keys()
        )

    def test_run_callback_fn_exception(self) -> None:
        """
        Test _run_callback_fn exception handling
        """
        callback = DummyCallback("train")
        train_unit = MagicMock()
        dummy_train_state = MagicMock()

        with self.assertRaisesRegex(
            ValueError, "Invalid callback method name provided"
        ):
            _run_callback_fn([callback], "dummy_attr", dummy_train_state, train_unit)

        with self.assertRaisesRegex(
            AttributeError, "object has no attribute 'on_train_finish'"
        ):
            _run_callback_fn(
                [callback], "on_train_finish", dummy_train_state, train_unit
            )

    def test_step_func_requires_iterator(self) -> None:
        class Foo:
            def bar(self) -> None:
                pass

            def baz(self, data: Iterator[int], b: int, c: str) -> int:
                return b

        def dummy(a: int, b: str, data: Iterator[str]) -> None:
            pass

        foo = Foo()

        self.assertFalse(_step_requires_iterator(foo.bar))
        self.assertTrue(_step_requires_iterator(foo.baz))
        self.assertTrue(_step_requires_iterator(dummy))

    def test_is_done(self) -> None:
        p = Progress(
            num_epochs_completed=2,
            num_steps_completed=100,
            num_steps_completed_in_epoch=5,
        )

        self.assertTrue(_is_done(p, max_epochs=2, max_steps=200))
        self.assertTrue(_is_done(p, max_epochs=2, max_steps=None))
        self.assertTrue(_is_done(p, max_epochs=3, max_steps=100))
        self.assertTrue(_is_done(p, max_epochs=None, max_steps=100))

        self.assertFalse(_is_done(p, max_epochs=3, max_steps=200))
        self.assertFalse(_is_done(p, max_epochs=None, max_steps=200))
        self.assertFalse(_is_done(p, max_epochs=3, max_steps=None))
        self.assertFalse(_is_done(p, max_epochs=None, max_steps=None))

    def test_is_epoch_done(self) -> None:
        p = Progress(
            num_epochs_completed=2,
            num_steps_completed=100,
            num_steps_completed_in_epoch=5,
        )

        self.assertTrue(_is_epoch_done(p, max_steps_per_epoch=5, max_steps=200))
        self.assertTrue(_is_epoch_done(p, max_steps_per_epoch=5, max_steps=None))
        self.assertTrue(_is_epoch_done(p, max_steps_per_epoch=100, max_steps=100))
        self.assertTrue(_is_epoch_done(p, max_steps_per_epoch=None, max_steps=100))

        self.assertFalse(_is_epoch_done(p, max_steps_per_epoch=6, max_steps=200))
        self.assertFalse(_is_epoch_done(p, max_steps_per_epoch=None, max_steps=200))
        self.assertFalse(_is_epoch_done(p, max_steps_per_epoch=6, max_steps=None))
        self.assertFalse(_is_epoch_done(p, max_steps_per_epoch=None, max_steps=None))


class DummyCallback(Callback):
    def __init__(self, dummy_data: str) -> None:
        self.dummy_data = dummy_data
        self.dummy_attr = 1

    def on_exception(
        self,
        state: State,
        unit: Union[
            TrainUnit[TTrainData], EvalUnit[TEvalData], PredictUnit[TPredictData]
        ],
        exc: BaseException,
    ):
        self.dummy_data = "on_exception"

    def on_train_start(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        self.dummy_data = "on_train_start"

    def on_train_epoch_start(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        self.dummy_data = "on_train_epoch_start"

    def on_train_step_start(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        self.dummy_data = "on_train_step_start"

    def on_train_step_end(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        self.dummy_data = "on_train_step_end"

    def on_train_epoch_end(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        self.dummy_data = "on_train_epoch_end"

    def on_train_end(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        self.dummy_data = "on_train_end"
