import tensorflow as tf
import pandas as pd


def evaluate(model, word2id, id2word, step, path_submission):

    # Create Dataset
    ds_test = build_dataset(PATH_TEST, word2id)
    ds_test = dataset.batch(BATCH_SIZE)

    # Run Validation
    accuracy, perp = validate(model=model, dataset=ds_test, id2word=id2_word, step=step)

    # Write Submission File
    if path_submission is not None:
        perp = tf.concat(perp, axis=0)
        print(f"Writing Submission: {path_submission}")
        pd.DataFrame(perp.numpy()).to_csv(path_submission, sep=' ', header=False , index=False)


def validate(model, dataset, id2word, step):

    # Define Valid Metrics
    metrics = {}
    metrics['loss'] = tf.keras.metrics.Mean(name='valid_loss')
    metrics['accuracy'] = tf.keras.metrics.SparseCategoricalAccuracy(name='valid_accuracy')
    metrics['top5_accuracy'] = tf.metrics.SparseTopKCategoricalAccuracy(k=5, name="valid_top5_accuracy")
    metrics['total_perplexity'] = Perplexity(name="valid_total_perplexity")
    metrics['sentence_perplexity'] = Perplexity(name="valid_sentence_perplexity")

    perp = []

    # loop over dataset in batches
    for sentence, labels, mask in dataset:
        perplexities_batch = evaluate_step(sentence=sentence, labels=labels, mask=mask, id2word=id2word, metrics=metrics)
        perp.append(perplexities_batch)

    # log metrics after complete pass through dataset
    tf.summary.scalar('valid/loss', metrics['loss'].result(), step=step)
    tf.summary.scalar('valid/accuracy', metrics['accuracy'].result(), step=step)
    tf.summary.scalar('valid/top5_accuracy', metrics['top5_accuracy'].result(), step=step)
    tf.summary.scalar('valid/total_perplexity', metrics_valid['total_perplexity'].result(), step=step)

    # TODO define metric from which to choose if we want to save checkpoint
    return metrics['accuracy'].result(), perp



@tf.function
def evaluate_step(sentence, labels, mask, step, id2word, metrics):

    # fill the last element of validation set to BATCH_SIZE
    batch_size = tf.shape(sentence)[0]
    if  batch_size != BATCH_SIZE:
        sentence = tf.concat([sentence, tf.zeros((BATCH_SIZE-batch_size, SENTENCE_LENGTH-1), dtype=tf.int64)],axis=0)
        labels = tf.concat([labels, tf.zeros((BATCH_SIZE-batch_size, SENTENCE_LENGTH-1), dtype=tf.int64)],axis=0)
        mask = tf.concat([mask, tf.fill([BATCH_SIZE-batch_size, SENTENCE_LENGTH-1], False)],axis=0)

    logits = model(sentence)

    preds = tf.nn.softmax(logits)
    predicted_words = tf.math.argmax(logits, axis=2)

    # mask out padding
    logits_masked = tf.boolean_mask(logits, mask)
    labels_masked = tf.boolean_mask(labels, mask)

    # calculate masked loss
    loss = tf.nn.sparse_softmax_cross_entropy_with_logits(labels=labels_masked, logits=logits_masked)
    loss = tf.math.reduce_mean(loss)

    # update avg metrics
    metrics['loss'].update_state(loss)
    metrics['accuracy'].update_state(y_true=labels_masked, y_pred=logits_masked)
    metrics['top5_accuracy'].update_state(y_true=labels_masked, y_pred=logits_masked)

    perplexities = []

    for i in tf.range(BATCH_SIZE):

        # select sample from batch
        sentence_labels = labels[i,:]
        sentence_preds = preds[i, :, :]
        sentence_mask = mask[i,:]

        # mask out padding
        sentence_labels_masked = tf.boolean_mask(sentence_labels, sentence_mask)
        sentence_preds_masked = tf.boolean_mask(sentence_preds, sentence_mask)

        # update total perplexity metric
        metrics['total_perplexity'].update_state(y_true=sentence_labels_masked, y_pred=sentence_preds_masked)

        # calculate sentence level perplexity
        metrics['sentence_perplexity'].update_state(y_true=sentence_labels_masked, y_pred=sentence_preds_masked)
        perplexities.append(metrics['sentence_perplexity'].result())
        metrics['sentence_perplexity'].reset_states()

    # tensorboard text
    labels_text = format_to_text(words=labels, mask=mask, id2word=id2word)
    argmax_preds_text = format_to_text(words=predicted_words, mask=mask, id2word=id2word)
    perplexities_text = tf.stack(perplexities, axis=0)

    stacked_text = tf.stack([labels_text, perplexities_text, argmax_preds_text], axis=1)
    tf.summary.text('valid/text_gt_perp_pred', stacked_text, step=step)

    return perplexities

def format_to_text(words, mask, id2word):

    # convert from id to words
    words = id2word.lookup(words)

    # mask out padding
    words = tf.where(mask, words, tf.cast(tf.fill([BATCH_SIZE, SENTENCE_LENGTH-1], ""), dtype=tf.string))

    # join sentence
    sentence = tf.strings.reduce_join(inputs=words, axis=1, separator=" ") # \in [batch_size]

    return sentence
