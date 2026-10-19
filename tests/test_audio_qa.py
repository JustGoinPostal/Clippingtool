import numpy as np

from app.audio_qa import saturation_stats_from_pcm


def _pcm(values):
    return np.asarray(values,dtype="<i2").tobytes()


def test_pcm_saturation_distinguishes_loud_from_pinned_samples():
    loud=saturation_stats_from_pcm(_pcm([30000,-30000,28000,-28000]*100))
    assert loud["near_fullscale_ratio"] == 0.0
    assert loud["hard_fullscale_ratio"] == 0.0
    assert loud["longest_hard_run"] == 0

    clipped=saturation_stats_from_pcm(_pcm([0]*100+[32767]*40+[-32768]*40+[1000]*20))
    assert clipped["hard_fullscale_samples"] == 80
    assert clipped["hard_fullscale_ratio"] > 0.30
    assert clipped["longest_hard_run"] == 80
    assert clipped["max_abs"] == 32768


def test_pcm_saturation_handles_empty_and_odd_byte_buffers():
    empty=saturation_stats_from_pcm(b"")
    assert empty["sample_count"] == 0
    odd=saturation_stats_from_pcm(_pcm([32767,0])+b"x")
    assert odd["sample_count"] == 2
    assert odd["hard_fullscale_samples"] == 1
