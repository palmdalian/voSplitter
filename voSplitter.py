import wave
import audioop
import sys
import subprocess
import math
import os
import csv


# Adjustment parameters
head_adjust = 0.15
tail_adjust = 0.35
threshold = 100
silence_length = 0.7
min_sound_length = 0.5
sample_number = 50 #The bigger the number, the faster it goes (but loses accuracy)

class SoundFinder():
	def __init__(self, input_path):
		self.input_path = input_path
		root = os.path.dirname(self.input_path)
		base = os.path.basename(self.input_path)
		self.split = os.path.splitext(base)
		self.output = os.path.join(root, self.split[0])
		self.output_base = os.path.join(self.output, self.split[0])
		self.silence_list = []
		self.sound_list = []
		self.convertAudio = False
		self.prepare_wav()

	def prepare_wav(self):
		try:
			self.wav = wave.open(self.input_path)
			params = self.wav.getparams()
			# (nchannels, sampwidth, framerate, nframes, comptype, compname)
			if params[0] > 1 or params[1] not in [1,2,4]:
				self.convertAudio = True
		except:
			self.convertAudio = True

		# Create temp pcm file just in case it's not in the right format (24 bit pcm doesn't work here)
		if self.convertAudio is True:
			print("Converting file to 16 bit, mono wave")
			self.converted_path = self.output + "_temp.wav"
			args = ["ffmpeg", "-y", "-v", "quiet", "-i", self.input_path, "-vn", "-ac", "1", "-c:a", "pcm_s16le", self.converted_path]
			subprocess.check_call(args)
			self.wav = wave.open(self.converted_path)


	def find_sound(self):
		self.framerate = self.wav.getframerate()
		sample_width = self.wav.getsampwidth()
		sample_length = float(sample_number) / self.framerate
		frames = self.wav.readframes(sample_number)
		total_length = sample_length
		sequential = False

		while (frames):
			amplitute = audioop.rms(frames, sample_width)
			# Is the sample lower than the threshold?
			if amplitute < threshold:
				if sequential is False:
					sequential = True
					self.silence_list.append([total_length, total_length])
				self.silence_list[-1][1] = total_length
			# No, so we start a
			else:
				sequential = False
				self.silence_list.append([total_length, total_length])
				if len(self.silence_list) and (self.silence_list[-1][1] - self.silence_list[-1][0]) < silence_length:
					self.silence_list.pop(-1)

			frames = self.wav.readframes(sample_number)
			total_length += sample_length

		# Go through and make time adjustments, getting rid of false stops
		pop_list = []
		for i, mark in enumerate(self.silence_list):
			if (mark[1]-mark[0]) < silence_length:
				pop_list.append(i)
			else:
				mark[0] - head_adjust
				mark[1] + tail_adjust

		for i in reversed(pop_list):
			self.silence_list.pop(i)

		# As of right now, this is a silence list (which is easier to get).
		# Next have to change it into a sound list
		for i in xrange(0, len(self.silence_list)):
			if i+1 < len(self.silence_list):
				self.sound_list.append([self.silence_list[i][1], self.silence_list[i+1][0]])

		# One last pass to get rid of sounds that are too short
		pop_list = []
		for i, mark in enumerate(self.sound_list):
			if (mark[1]-mark[0]) < min_sound_length:
				pop_list.append(i)

		for i in reversed(pop_list):
			self.sound_list.pop(i)


	def save_chunks(self):
		# Save out the chunks
		print("Splitting file " + self.split[0])
		if not os.path.exists(self.output):
			os.mkdir(self.output)
		for i, sound in enumerate(self.sound_list):
			start_sample = int(math.floor(sound[0] * self.framerate))
			end_sample = int(math.ceil(sound[1] * self.framerate))
			self.wav.rewind()
			self.wav.readframes(start_sample) # Go to the start point
			frames = self.wav.readframes(end_sample-start_sample)

			outpath = "{output_base}_{num}.wav".format(output_base=self.output_base, num=str(i).zfill(3))
			wavout = wave.open(outpath, 'wb')
			wavout.setparams(self.wav.getparams())
			wavout.writeframes(frames)
			wavout.close()
		self.wav.close()

		with open(self.output_base + "_editlist.csv", 'w') as f:
			writer = csv.writer(f)
			settings = "# head_adjust={head_adjust}, tail_adjust={tail_adjust}, threshold={threshold}, silence_length={silence_length}, min_sound_length={min_sound_length}, sample_number={sample_number}".format(head_adjust=head_adjust, tail_adjust=tail_adjust, threshold=threshold, silence_length=silence_length, min_sound_length=min_sound_length, sample_number=sample_number)
			writer.writerows([[settings]])
			writer.writerows(self.sound_list)
		if self.convertAudio is True:
			os.remove(self.converted_path)

if __name__ == '__main__':
	accepted_files = ['.aiff', '.wav', '.mp3', '.aif']
	input_paths = []
	input_path = sys.argv[1]

	if not os.path.isdir(input_path):
		base = os.path.basename(input_path)
		split = os.path.splitext(base)
		if split[-1] in accepted_files:
			input_paths.append(input_path)
	else:
		input_paths = [os.path.join(input_path, x) for x in os.listdir(input_path) if not x.startswith('.') and os.path.splitext(x)[-1] in accepted_files]

	for path in input_paths:
		print path
		finder = SoundFinder(path)
		finder.find_sound()
		finder.save_chunks()
